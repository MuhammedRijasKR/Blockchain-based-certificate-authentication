import hashlib
import os
import json

import streamlit as st
from connection import contract
from utils.cert_utils import extract_certificate
from utils.auth import AuthManager
from utils.streamlit_utils import hide_sidebar
from utils.crypto_utils import DigitalCertificateAuth
from utils.face_utils import get_face_profile, verify_face_match
from utils.face_hash import hash_face_profile
from utils.merkle_utils import find_certificate_batch, verify_merkle_proof, compute_leaf
from utils.encryption_utils import try_decrypt_with_all_keys
from utils.bloom_filter import bloom_check

hide_sidebar()
auth = AuthManager()
crypto_auth = DigitalCertificateAuth()

auth.require_auth(allowed_roles=("verifier",))

st.markdown("<h2 style='text-align: center;'>✅ Certificate Verification</h2>", unsafe_allow_html=True)
st.markdown("##")


def _find_batch_cert_by_fields(uid, candidate_name, course_name, org_name, grade=""):
    """Search Merkle proof store for a certificate matching the given fields."""
    from utils.merkle_utils import _load_store
    store = _load_store()
    matches = []
    for batch_id, batch_data in store.items():
        for cert_id, cert in batch_data["certificates"].items():
            if (cert["uid"] == uid and cert["candidate_name"] == candidate_name and 
                cert["course_name"] == course_name and cert["org_name"] == org_name):
                matches.append(cert_id)
    return matches


def _show_verification_result(is_valid, is_revoked, candidate_name, org_name, course_name, grade, signature_valid, institute_name, institute_verified):
    """Display a clean verification result."""
    st.markdown("---")
    st.markdown("### 📋 Verification Result")

    if is_revoked:
        st.error("❌ Certificate has been **REVOKED** and is no longer valid.")
        return

    if not is_valid:
        st.error("❌ Certificate is **INVALID** or not found.")
        return

    st.success("🎉 Certificate is **VALID** and registered on blockchain.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Candidate Name:** {candidate_name}")
        st.markdown(f"**Course:** {course_name}")
        if grade:
            st.markdown(f"**Grade:** {grade}")
    with col2:
        st.markdown(f"**Organization:** {org_name}")
        if institute_name:
            st.markdown(f"**Institute:** {institute_name}")

    if signature_valid:
        st.success("🔐 Digital signature is **VALID** — Certificate is authentic!")
    else:
        st.error("❌ Digital signature is **INVALID** — Certificate may be tampered!")

    if institute_verified:
        st.success("✅ Issuing institute is verified by the system")
    elif institute_name:
        st.warning("⚠️ Issuing institute is not yet verified")


def _gate_owner_face(certificate_id, owner_name="", expected_face_hash=None):
    """Live face match against the certificate's bound profile.

    ``expected_face_hash`` is the on-chain digest (bytes) for individual certs
    or the hex string from the Merkle leaf for batch certs. When provided, we
    refuse to verify if the local profile's hash does not match -- that means
    the off-chain profile was tampered with after issuance.
    """
    profile = get_face_profile(certificate_id)

    # Compare the local profile hash to the issuer-anchored hash whenever we
    # have one. A mismatch (or a missing local profile when one was bound on
    # chain) is a hard failure.
    if expected_face_hash:
        local_digest = hash_face_profile(certificate_id)
        if isinstance(expected_face_hash, (bytes, bytearray)):
            expected_hex = bytes(expected_face_hash).hex()
        else:
            expected_hex = str(expected_face_hash).lower().lstrip("0x")
        if local_digest is None:
            st.error(
                "❌ This certificate has a face profile bound on-chain, but the local "
                "face profile is missing. Identity-of-bearer cannot be verified."
            )
            return False
        if local_digest.hex() != expected_hex:
            st.error(
                "❌ Face profile integrity check failed: the local profile does not "
                "match the hash anchored at issuance. The profile may have been tampered with."
            )
            return False

    if not profile:
        # No on-chain hash AND no local profile -- treat as a missing biometric
        # binding. Hard-fail rather than silently proceed.
        st.error(
            "❌ This certificate has no biometric profile bound to it. "
            "Identity-of-bearer cannot be established; rejecting."
        )
        return False

    display_name = profile.get("owner_name") or owner_name or "the certificate owner"
    st.markdown("### 🧑‍💼 Live Face ID Verification")
    st.caption(
        f"Capture a live photo of **{display_name}**. The image must match the face the issuing "
        f"institute bound to this certificate."
    )

    live_face = st.camera_input(
        "Capture the certificate owner's face",
        key=f"verifier_face_{certificate_id}",
    )
    if live_face is None:
        st.info("👆 Take a live photo to continue.")
        return None

    is_match, confidence, message = verify_face_match(certificate_id, live_face.getvalue())
    if not is_match:
        st.error(f"❌ {message}")
        if confidence is not None:
            st.caption("Tip: ensure good lighting, frontal pose, and a single face in frame.")
        return False

    st.success(f"✅ {message}")
    return True


def _confirm_face_after_authenticity(certificate_id, owner_name="", expected_face_hash=None):
    """Prompt for live Face ID only after certificate authenticity passes."""
    st.markdown("---")
    st.success("✅ Authenticity checks passed. Continue with live Face ID to confirm the holder.")
    face_gate = _gate_owner_face(
        certificate_id,
        owner_name,
        expected_face_hash=expected_face_hash,
    )
    if face_gate is not True:
        st.stop()
    st.success("✅ Face matched. This certificate belongs to the captured person.")


def _verify_batch_certificate(batch_id, batch_cert_data, certificate_id, salt, uid, candidate_name, course_name, org_name, grade=""):
    """Verify a certificate that belongs to a Merkle batch."""
    face_hash_hex = batch_cert_data.get("face_hash", "") or ""
    if not face_hash_hex:
        local_face_digest = hash_face_profile(certificate_id)
        if local_face_digest is not None:
            face_hash_hex = local_face_digest.hex()

    expected_leaf = compute_leaf(
        salt, uid, candidate_name, course_name, org_name, grade,
        face_hash=face_hash_hex,
    )
    if expected_leaf != batch_cert_data["leaf_hash"]:
        legacy_leaf = compute_leaf(salt, uid, candidate_name, course_name, org_name, grade)
        if legacy_leaf == batch_cert_data["leaf_hash"]:
            expected_leaf = legacy_leaf
            face_hash_hex = ""
        else:
            st.error("❌ Certificate hash mismatch - data may have been tampered!")
            return

    try:
        batch_data = contract.functions.getBatch(int(batch_id)).call()
        on_chain_root = batch_data[0].hex()
        is_approved = batch_data[3]

        proof = batch_cert_data["proof"]
        proof_valid = verify_merkle_proof(expected_leaf, proof, on_chain_root)

        if not proof_valid:
            _show_verification_result(False, False, candidate_name, org_name, course_name, grade, False, None, False)
            return

        if not is_approved:
            st.warning("⏳ Certificate batch is **PENDING** admin approval. Not yet active.")
            return

        is_revoked = contract.functions.isRevoked(certificate_id).call()
        if is_revoked:
            _show_verification_result(False, True, candidate_name, org_name, course_name, grade, False, None, False)
            return

        # Get institute info
        institute_email = batch_data[1]
        institute_name = ""
        institute_verified = False
        try:
            institute_info = contract.functions.getInstitute(institute_email).call()
            institute_name = institute_info[0]
            institute_verified = institute_info[2]
        except:
            pass

        _show_verification_result(True, False, candidate_name, org_name, course_name, grade, True, institute_name, institute_verified)
        _confirm_face_after_authenticity(
            certificate_id,
            candidate_name,
            expected_face_hash=face_hash_hex or None,
        )

    except Exception as e:
        st.error(f"❌ Verification failed: {str(e)}")


def _verify_by_certificate_id(certificate_id: str):
    """Run the full verification flow for a given certificate_id.

    Used by both the "Verify using Certificate ID" tab and the
    "Verify using QR Code" tab (after the QR is decoded).
    """
    # Bloom Filter pre-check — useful hint only. The local Bloom file can
    # be stale after reset/migration, so never stop before checking the
    # chain and Merkle store.
    if not bloom_check(certificate_id):
        st.warning("⚠️ Bloom Filter did not contain this ID. Continuing with blockchain/Merkle lookup...")

    # First check if it's a batch certificate
    batch_id, batch_cert_data = find_certificate_batch(certificate_id)
    if batch_id is not None:
        salt = batch_cert_data["salt"]
        uid = batch_cert_data["uid"]
        candidate_name = batch_cert_data["candidate_name"]
        course_name = batch_cert_data["course_name"]
        org_name = batch_cert_data["org_name"]
        grade = batch_cert_data.get("grade", "")
        _verify_batch_certificate(batch_id, batch_cert_data, certificate_id, salt, uid, candidate_name, course_name, org_name, grade)
        return

    # Individual cert verification
    try:
        cert_data = contract.functions.getCertificate(certificate_id).call()
        try:
            _onchain_fh = contract.functions.certificateFaceHash(certificate_id).call()
        except Exception:
            _onchain_fh = b"\x00" * 32
        _expected_fh = bytes(_onchain_fh) if any(_onchain_fh) else None
        is_revoked = contract.functions.isRevoked(certificate_id).call()

        institute_email = cert_data[5]
        digital_signature = cert_data[6]
        cert_grade = cert_data[8]

        certificate_data = {
            "uid": cert_data[0],
            "candidate_name": cert_data[1],
            "course_name": cert_data[2],
            "org_name": cert_data[3],
            "ipfs_hash": cert_data[4],
            "certificate_id": certificate_id,
            "salt": cert_data[7],
            "grade": cert_grade,
        }

        signature_valid = crypto_auth.verify_certificate_signature(
            institute_email, certificate_data, digital_signature
        )

        institute_name = ""
        institute_verified = False
        try:
            institute_info = contract.functions.getInstitute(institute_email).call()
            institute_name = institute_info[0]
            institute_verified = institute_info[2]
        except Exception:
            pass

        result = contract.functions.isVerified(certificate_id).call()
        _show_verification_result(
            result, is_revoked,
            cert_data[1], cert_data[3], cert_data[2], cert_grade,
            signature_valid, institute_name, institute_verified,
        )

        if result and not is_revoked and signature_valid:
            _confirm_face_after_authenticity(
                certificate_id,
                cert_data[1],
                expected_face_hash=_expected_fh,
            )

    except Exception as e:
        print(e)
        st.error("❌ Error validating certificate. Please check the Certificate ID.")


# --- Options ---
options = ("Verify using PDF", "Verify using Certificate ID", "Verify using QR Code", "Institute Verification")
selected = st.selectbox("Select an option", options, label_visibility="collapsed")

# --- Option 1: Upload Certificate PDF ---
if selected == options[0]:
    uploaded_file = st.file_uploader("Upload your Certificate (PDF or encrypted .enc file)")

    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        pdf_bytes = None
        is_encrypted = False

        # Try to parse as PDF first
        try:
            with open("temp_certificate.pdf", "wb") as file:
                file.write(file_bytes)
            uid, candidate_name, course_name, org_name, grade = extract_certificate("temp_certificate.pdf")
            os.remove("temp_certificate.pdf")
            pdf_bytes = file_bytes
        except Exception:
            # PDF parsing failed — try decrypting as encrypted file
            is_encrypted = True
            try:
                decrypted_bytes, matched_cert_id = try_decrypt_with_all_keys(file_bytes)
                if decrypted_bytes:
                    with open("temp_certificate.pdf", "wb") as file:
                        file.write(decrypted_bytes)
                    uid, candidate_name, course_name, org_name, grade = extract_certificate("temp_certificate.pdf")
                    os.remove("temp_certificate.pdf")
                    pdf_bytes = decrypted_bytes
                else:
                    st.error("❌ Could not process file. It is neither a valid PDF nor a recognized encrypted certificate.")
                    st.stop()
            except Exception:
                if os.path.exists("temp_certificate.pdf"):
                    os.remove("temp_certificate.pdf")
                st.error("❌ Could not process this file. It might be corrupted or not a valid certificate.")
                st.stop()

        try:
            st.info("📄 Certificate data extracted. Verifying on blockchain...")

            # Try to find in individual certificates first
            all_cert_ids = contract.functions.getAllCertificateIds().call()
            certificate_id = None
            salt = None
            cert_grade = grade
            
            for cid in all_cert_ids:
                try:
                    cd = contract.functions.getCertificate(cid).call()
                    if cd[0] == uid and cd[1] == candidate_name and cd[2] == course_name and cd[3] == org_name:
                        certificate_id = cid
                        salt = cd[7]
                        cert_grade = cd[8]
                        break
                except Exception:
                    continue

            # Also check pending certificates
            if certificate_id is None:
                try:
                    pending_ids = contract.functions.getAllPendingCertificateIds().call()
                    for cid in pending_ids:
                        try:
                            cd = contract.functions.getCertificate(cid).call()
                            if cd[0] == uid and cd[1] == candidate_name and cd[2] == course_name and cd[3] == org_name:
                                certificate_id = cid
                                salt = cd[7]
                                cert_grade = cd[8]
                                break
                        except Exception:
                            continue
                except:
                    pass
            
            if certificate_id is None:
                # Check if this cert exists in a Merkle batch
                for batch_cert_id_candidate in _find_batch_cert_by_fields(uid, candidate_name, course_name, org_name, grade):
                    batch_id, batch_cert_data = find_certificate_batch(batch_cert_id_candidate)
                    if batch_id is not None:
                        certificate_id = batch_cert_id_candidate
                        salt = batch_cert_data["salt"]
                        cert_grade = batch_cert_data.get("grade", "")
                        break

            if certificate_id is None:
                st.error("❌ Certificate not found on blockchain or in any batch.")
                st.stop()

            # Lookup the on-chain face hash anchor (individual certs only).
            try:
                _onchain_fh = contract.functions.certificateFaceHash(certificate_id).call()
            except Exception:
                _onchain_fh = b"\x00" * 32
            _expected_fh = bytes(_onchain_fh) if any(_onchain_fh) else None

            # Check if it's a batch certificate
            batch_id, batch_cert_data = find_certificate_batch(certificate_id)
            if batch_id is not None:
                _expected_fh = batch_cert_data.get("face_hash") or None

            if batch_id is not None:
                _verify_batch_certificate(batch_id, batch_cert_data, certificate_id, salt, uid, candidate_name, course_name, org_name, cert_grade)
                st.stop()

            # Individual certificate verification
            data_to_hash = f"{salt}{uid}{candidate_name}{course_name}{org_name}{cert_grade}".encode('utf-8')
            expected_hash = hashlib.sha256(data_to_hash).hexdigest()
            
            if expected_hash != certificate_id:
                st.error("❌ Certificate hash mismatch - data may have been tampered!")
                st.stop()

            try:
                cert_data = contract.functions.getCertificate(certificate_id).call()
                is_revoked = contract.functions.isRevoked(certificate_id).call()
                
                institute_email = cert_data[5]
                digital_signature = cert_data[6]
                
                certificate_data = {
                    "uid": uid,
                    "candidate_name": candidate_name,
                    "course_name": course_name,
                    "org_name": org_name,
                    "ipfs_hash": cert_data[4],
                    "certificate_id": certificate_id,
                    "salt": salt,
                    "grade": cert_grade
                }
                
                signature_valid = crypto_auth.verify_certificate_signature(
                    institute_email, certificate_data, digital_signature
                )
                
                institute_name = ""
                institute_verified = False
                try:
                    institute_info = contract.functions.getInstitute(institute_email).call()
                    institute_name = institute_info[0]
                    institute_verified = institute_info[2]
                except:
                    pass

                result = contract.functions.isVerified(certificate_id).call()
                _show_verification_result(result, is_revoked, candidate_name, org_name, course_name, cert_grade, signature_valid, institute_name, institute_verified)

                if result and not is_revoked and signature_valid:
                    _confirm_face_after_authenticity(
                        certificate_id,
                        candidate_name,
                        expected_face_hash=_expected_fh,
                    )
                        
            except Exception as e:
                st.error("❌ Certificate not found on blockchain.")

        except Exception as e:
            st.error("❌ Could not process this certificate. It might be tampered or corrupted.")

# --- Option 2: Enter Certificate ID ---
elif selected == options[1]:
    with st.form("Validate-Certificate"):
        st.markdown("#### Enter the Certificate ID to verify")
        certificate_id = st.text_input("Certificate ID", value=st.session_state.get("verify_certificate_id", ""))
        submit = st.form_submit_button("Verify")

    if submit:
        if not certificate_id.strip():
            st.warning("Please enter a certificate ID.")
            st.session_state.pop("verify_certificate_id", None)
        else:
            st.session_state["verify_certificate_id"] = certificate_id.strip()

    certificate_id = st.session_state.get("verify_certificate_id")
    if certificate_id:
        _verify_by_certificate_id(certificate_id)

# --- Option 3: Verify using QR Code ---
elif selected == options[2]:
    from utils.qr_utils import decode_qr_from_bytes

    st.markdown("#### Upload a QR code image to verify")
    st.caption("Take a screenshot/photo of the QR on the certificate, or use the QR PNG downloaded from the institute.")
    qr_file = st.file_uploader("QR code image", type=["png", "jpg", "jpeg", "bmp", "webp"], key="qr_verify_upload")

    if qr_file is not None:
        try:
            decoded = decode_qr_from_bytes(qr_file.getvalue())
        except Exception as exc:
            decoded = None
            st.error(f"❌ Could not read QR image: {exc}")

        if decoded is None:
            pass  # error already shown
        elif not decoded:
            st.error("❌ No QR code detected in the image. Try a clearer / less blurry capture.")
        else:
            decoded_id = decoded.strip()
            st.success(f"✅ QR decoded. Certificate ID: `{decoded_id}`")
            _verify_by_certificate_id(decoded_id)

# --- Option 4: Institute Verification ---
elif selected == options[3]:
    st.markdown("### 🏛️ Institute Verification")
    st.write("Verify if an institute is registered and verified in the system.")
    
    with st.form("Institute-Verification"):
        institute_email = st.text_input("Institute Email")
        submit = st.form_submit_button("Verify Institute")
    
    if submit:
        if not institute_email.strip():
            st.warning("Please enter an institute email.")
        else:
            try:
                institute_info = contract.functions.getInstitute(institute_email).call()
                
                st.success("✅ Institute found in the system!")
                st.write(f"**Institute Name**: {institute_info[0]}")
                st.write(f"**Email**: {institute_email}")
                st.write(f"**Registration Date**: {institute_info[3]}")
                
                if institute_info[2]:
                    st.success("✅ Institute is VERIFIED and can issue certificates")
                else:
                    st.warning("⚠️ Institute is NOT VERIFIED yet")
                
                public_key = institute_info[1]
                if public_key:
                    st.text_area("Public Key", public_key, height=150)
                
            except Exception as e:
                st.error("❌ Institute not found in the system.")
