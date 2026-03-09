import hashlib
import os
import json

import streamlit as st
from connection import contract
from utils.cert_utils import extract_certificate
from utils.auth import AuthManager
from utils.streamlit_utils import hide_sidebar
from utils.crypto_utils import DigitalCertificateAuth
from utils.merkle_utils import find_certificate_batch, verify_merkle_proof, compute_leaf
from utils.encryption_utils import try_decrypt_with_all_keys

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


def _verify_batch_certificate(batch_id, batch_cert_data, certificate_id, salt, uid, candidate_name, course_name, org_name, grade=""):
    """Verify a certificate that belongs to a Merkle batch."""
    expected_leaf = compute_leaf(salt, uid, candidate_name, course_name, org_name, grade)
    if expected_leaf != batch_cert_data["leaf_hash"]:
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

    except Exception as e:
        st.error(f"❌ Verification failed: {str(e)}")


# --- Options ---
options = ("Verify using PDF", "Verify using Certificate ID", "Institute Verification")
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

            # Check if it's a batch certificate
            batch_id, batch_cert_data = find_certificate_batch(certificate_id)
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
                        
            except Exception as e:
                st.error("❌ Certificate not found on blockchain.")

        except Exception as e:
            st.error("❌ Could not process this certificate. It might be tampered or corrupted.")

# --- Option 2: Enter Certificate ID ---
elif selected == options[1]:
    with st.form("Validate-Certificate"):
        st.markdown("#### Enter the Certificate ID to verify")
        certificate_id = st.text_input("Certificate ID")
        submit = st.form_submit_button("Verify")

    if submit:
        if not certificate_id.strip():
            st.warning("Please enter a certificate ID.")
        else:
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
            else:
                # Individual cert verification
                try:
                    cert_data = contract.functions.getCertificate(certificate_id).call()
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
                    _show_verification_result(
                        result, is_revoked,
                        cert_data[1], cert_data[3], cert_data[2], cert_grade,
                        signature_valid, institute_name, institute_verified
                    )
                        
                except Exception as e:
                    print(e)
                    st.error("❌ Error validating certificate. Please check the Certificate ID.")

# --- Option 3: Institute Verification ---
elif selected == options[2]:
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
