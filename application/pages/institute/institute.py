import hashlib
import os
import json
import re
import zipfile
from io import BytesIO

import streamlit as st
from connection import contract, w3
from dotenv import load_dotenv
from utils.auth import AuthManager
from utils.cert_utils import generate_certificate, get_certificate_id_ipfs_hash
from utils.pinata_utils import upload_to_pinata, upload_bytes_to_pinata, delete_pinata_file, get_pinata_files
from utils.face_utils import save_face_samples, get_face_profile, enroll_face_for_cert, clear_face_profile, detect_face
from utils.face_hash import hash_face_profile
from utils.streamlit_utils import hide_sidebar
from utils.streamlit_utils import view_certificate, get_next_uid, uid_created
from utils.qr_utils import make_qr_png_bytes
from utils.crypto_utils import DigitalCertificateAuth
from utils.encryption_utils import generate_key, encrypt_file, save_encryption_key, get_encryption_key, decrypt_file
from utils.merkle_utils import compute_leaf, build_merkle_tree, save_batch_proofs
from utils.merkle_utils import find_certificate_batch, _load_store as load_merkle_store
from utils.bloom_filter import bloom_add
from utils.rejection_remarks import (
    get_batch_rejection,
    get_batch_rejections_for_institute,
    get_institute_rejection,
    get_rejection,
    get_rejections_for_institute,
    get_revocation_rejection,
    remove_rejection,
    remove_revocation_rejection,
)
from utils.tx_utils import send_tx
from utils.institute_signer import get_institute_signer

hide_sidebar()
auth = AuthManager()
crypto_auth = DigitalCertificateAuth()

auth.require_auth(allowed_roles=("institute",))

load_dotenv()


def _safe_filename(value):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return cleaned.strip("_") or "certificate"


def _build_certificates_zip(certificates, zip_title="certificates"):
    import requests

    zip_buffer = BytesIO()
    added = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for cert in certificates:
            certificate_id = cert["certificate_id"]
            candidate_name = cert.get("candidate_name") or cert.get("name") or certificate_id[:12]
            safe_name = _safe_filename(candidate_name)

            try:
                qr_bytes = make_qr_png_bytes(certificate_id)
                zf.writestr(f"{safe_name}_{certificate_id[:12]}_qr.png", qr_bytes)
            except Exception as exc:
                st.warning(f"⚠️ Could not create QR for {candidate_name}: {exc}")

            ipfs_hash = cert.get("ipfs_hash")
            if not ipfs_hash:
                continue

            try:
                enc_key = get_encryption_key(certificate_id, st.session_state.user_email, "institute")
                if not enc_key:
                    st.warning(f"⚠️ No encryption key for {candidate_name}")
                    continue

                response = requests.get(f"https://gateway.pinata.cloud/ipfs/{ipfs_hash}", timeout=60)
                if response.status_code != 200:
                    st.warning(f"⚠️ Could not download certificate for {candidate_name}")
                    continue

                pdf_bytes = decrypt_file(response.content, enc_key)
                zf.writestr(f"{safe_name}_{certificate_id[:12]}.pdf", pdf_bytes)
                added += 1
            except Exception as exc:
                st.warning(f"⚠️ Error processing {candidate_name}: {exc}")

    zip_buffer.seek(0)
    return zip_buffer.getvalue(), added, f"{_safe_filename(zip_title)}.zip"


def _matches_search_text(*values, query):
    if not query:
        return True
    haystack = " ".join(str(v or "") for v in values).lower()
    return query.lower() in haystack

# Check if the current user is already registered as an institute
is_registered = False
is_verified = False
try:
    institute_info = contract.functions.getInstitute(st.session_state.user_email).call()
    if institute_info[0]:  # If name exists
        is_registered = True
        is_verified = institute_info[2]  # is_verified field
except Exception:
    is_registered = False
    is_verified = False

# Show verification status banner
if is_registered and not is_verified:
    st.warning("""⏳ **Pending Verification**
    
Your institute registration is pending admin verification. You will be able to issue certificates once verified.
    
Please wait for an admin to verify your institute.""")
    st.markdown("---")

# Only show registration option if not registered
# Only show certificate options if verified
if is_registered and is_verified:
    options = [
        "Generate Certificate",
        "Face ID Enrollment",
        "Bulk Generate",
        "List Of Certificate",
        "View Certificates"
    ]
elif is_registered and not is_verified:
    options = [
        "View Verification Status",
        "View Certificates"
    ]
else:
    options = [
        "Institute Registration"
    ]

# If redirected from reapply, force selectbox to "Generate Certificate"
if st.session_state.get("selected_page") in options:
    st.session_state["institute_nav"] = st.session_state.pop("selected_page")

selected = st.selectbox(
    "Select an option", options, label_visibility="collapsed",
    key="institute_nav"
)

# --- Institute Registration ---
if selected == "Institute Registration":
    st.markdown("### 🏛️ Institute Registration")
    st.write("Register your institute to issue digitally signed certificates.")
    st.info("📋 Please provide accurate details. An admin will review and verify your registration.")
    
    with st.form("Institute-Registration"):
        st.markdown("#### Basic Information")
        institute_name = st.text_input("Institute Name *", placeholder="e.g., ABC University")
        institute_email = st.text_input("Institute Email", value=st.session_state.user_email, disabled=True)
        
        col1, col2 = st.columns(2)
        with col1:
            institute_type = st.selectbox(
                "Institute Type *",
                ["Select Type", "University", "College", "Technical Institute", 
                 "Training Center", "School", "Research Institute", "Other"]
            )
        with col2:
            established_year = st.text_input("Year Established", placeholder="e.g., 1990")
        
        st.markdown("#### Contact Information")
        col3, col4 = st.columns(2)
        with col3:
            phone_number = st.text_input("Phone Number *", placeholder="e.g., +91 9876543210")
        with col4:
            website = st.text_input("Official Website", placeholder="e.g., https://www.example.edu")
        
        address = st.text_area("Full Address *", placeholder="Street, City, State, Country, PIN Code", height=80)
        
        st.markdown("#### Verification Documents")
        col5, col6 = st.columns(2)
        with col5:
            registration_number = st.text_input(
                "Registration/License Number *", 
                placeholder="e.g., UGC-123456 or AICTE-789"
            )
        with col6:
            accreditation = st.text_input(
                "Accreditation (if any)", 
                placeholder="e.g., NAAC A+, NBA"
            )
        
        st.markdown("#### Contact Person")
        col7, col8 = st.columns(2)
        with col7:
            contact_person_name = st.text_input("Contact Person Name *", placeholder="e.g., Dr. John Smith")
        with col8:
            contact_person_designation = st.text_input("Designation *", placeholder="e.g., Registrar")
        
        contact_person_phone = st.text_input("Contact Person Phone", placeholder="e.g., +91 9876543210")
        
        # Generate keys if not exists
        private_key_path, public_key_path = crypto_auth.get_institute_keys(institute_email)
        if not os.path.exists(private_key_path):
            crypto_auth.generate_institute_keys(institute_email)
            st.success("✅ Cryptographic keys generated for your institute.")
        
        # Display public key
        if os.path.exists(public_key_path):
            with open(public_key_path, 'r') as f:
                public_key = f.read()
            with st.expander("View Your Public Key"):
                st.code(public_key, language="text")
        
        st.markdown("---")
        submit = st.form_submit_button("Submit Registration", type="primary", use_container_width=True)
        
        if submit:
            # Validation
            required_fields = [
                (institute_name, "Institute Name"),
                (institute_type != "Select Type", "Institute Type"),
                (phone_number, "Phone Number"),
                (address, "Address"),
                (registration_number, "Registration/License Number"),
                (contact_person_name, "Contact Person Name"),
                (contact_person_designation, "Contact Person Designation"),
            ]
            
            missing = [name for value, name in required_fields if not value]
            
            if missing:
                st.warning(f"⚠️ Please fill required fields: {', '.join(missing)}")
            else:
                try:
                    # Save additional details to JSON
                    from utils.institute_details import save_institute_details
                    
                    details = {
                        "institute_name": institute_name,
                        "institute_type": institute_type,
                        "established_year": established_year,
                        "phone_number": phone_number,
                        "website": website,
                        "address": address,
                        "registration_number": registration_number,
                        "accreditation": accreditation,
                        "contact_person_name": contact_person_name,
                        "contact_person_designation": contact_person_designation,
                        "contact_person_phone": contact_person_phone,
                    }
                    save_institute_details(institute_email, details)
                    
                    # Register institute on blockchain (pending verification).
                    # The msg.sender becomes the institute's bound signer for
                    # all subsequent on-chain actions.
                    institute_signer = get_institute_signer(institute_email)
                    if not institute_signer:
                        st.error("❌ No free Ganache account available to bind as institute signer.")
                        st.stop()
                    send_tx(
                        contract.functions.registerInstitute(
                            institute_email,
                            institute_name,
                            public_key,
                        ),
                        institute_signer,
                    )
                    st.success("✅ Institute registered successfully!")
                    st.info("🕐 Your registration is pending admin verification. You will be notified once verified.")
                    st.session_state["_institute_registered"] = True
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Registration failed: {str(e)}")

# --- View Verification Status ---
elif selected == "View Verification Status":
    st.markdown("### 📋 Verification Status")
    
    try:
        institute_info = contract.functions.getInstitute(st.session_state.user_email).call()
        name, public_key, is_verified_status, registered_at = institute_info
        institute_rejection = get_institute_rejection(st.session_state.user_email)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Institute Name:** {name}")
            st.markdown(f"**Email:** {st.session_state.user_email}")
        with col2:
            if is_verified_status:
                st.success("✅ **Status:** Verified")
            elif institute_rejection:
                st.error("❌ **Status:** Rejected")
            else:
                st.warning("⏳ **Status:** Pending Verification")
        
        from datetime import datetime
        reg_date = datetime.fromtimestamp(registered_at)
        st.markdown(f"**Registered On:** {reg_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if institute_rejection:
            st.error(f"**Admin Remarks:** {institute_rejection.get('remarks', '')}")
            st.caption(f"Rejected on: {institute_rejection.get('rejected_at', '')[:19]}")
            st.info("Review the remarks and contact an admin before submitting another verification request.")
        elif not is_verified_status:
            st.info("""💡 **What happens next?**
            
1. An admin will review your registration
2. Once verified, you'll be able to generate certificates
3. Check back here to see your updated status""")
    except Exception as e:
        st.error(f"❌ Error loading status: {str(e)}")

# --- Certificate List ---
elif selected == "List Of Certificate":
    files = get_pinata_files(st.session_state.user_email)

    if not files:
        st.info("No files found.")
    else:
        # --- Pre-process: classify files into individual certs and batch groups ---
        merkle_store = load_merkle_store()
        individual_files = []       # (file, certificate_id)
        batch_groups = {}           # batch_id -> list of (file, certificate_id, cert_meta)
        unknown_files = []          # files not on blockchain at all

        for f in files:
            ipfs_hash = f['ipfs_pin_hash']
            certificate_id = get_certificate_id_ipfs_hash(ipfs_hash)

            if not certificate_id:
                unknown_files.append(f)
                continue

            # Check if this cert belongs to a batch
            found_batch = None
            for bid, bdata in merkle_store.items():
                if certificate_id in bdata.get("certificates", {}):
                    found_batch = bid
                    break

            if found_batch is not None:
                if found_batch not in batch_groups:
                    batch_groups[found_batch] = []
                batch_groups[found_batch].append((f, certificate_id, merkle_store[found_batch]["certificates"][certificate_id]))
            else:
                individual_files.append((f, certificate_id))

        search_query = st.text_input(
            "Search certificates",
            placeholder="Search by candidate name, organization, or course",
            key="certificate_list_search",
        ).strip()

        if search_query:
            filtered_individual_files = []
            for f, certificate_id in individual_files:
                file_name = f["metadata"].get("name", "")
                try:
                    cert_data = contract.functions.getCertificate(certificate_id).call()
                    search_values = (file_name, cert_data[1], cert_data[2], cert_data[3])
                except Exception:
                    search_values = (file_name, certificate_id)
                if _matches_search_text(*search_values, query=search_query):
                    filtered_individual_files.append((f, certificate_id))

            filtered_batch_groups = {}
            for batch_id, batch_certs in batch_groups.items():
                matches = []
                for f, certificate_id, cert_meta in batch_certs:
                    if _matches_search_text(
                        cert_meta.get("candidate_name", ""),
                        cert_meta.get("course_name", ""),
                        cert_meta.get("org_name", ""),
                        f["metadata"].get("name", ""),
                        query=search_query,
                    ):
                        matches.append((f, certificate_id, cert_meta))
                if matches:
                    filtered_batch_groups[batch_id] = matches

            filtered_unknown_files = [
                f for f in unknown_files
                if _matches_search_text(f["metadata"].get("name", ""), query=search_query)
            ]

            individual_files = filtered_individual_files
            batch_groups = filtered_batch_groups
            unknown_files = filtered_unknown_files
            result_count = len(individual_files) + sum(len(v) for v in batch_groups.values()) + len(unknown_files)
            st.caption(f"Showing {result_count} matching item(s).")

        count = 1

        if search_query and not individual_files and not batch_groups and not unknown_files:
            st.info("No certificates matched your search.")

        # ===== INDIVIDUAL CERTIFICATES =====
        if individual_files:
            st.markdown("### 📜 Individual Certificates")
            for f, certificate_id in individual_files:
                name = f['metadata'].get('name', 'Unnamed')
                ipfs_hash = f['ipfs_pin_hash']
                link = f"https://gateway.pinata.cloud/ipfs/{ipfs_hash}"

                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([1, 3, 4, 2, 2])
                    col1.markdown(f"**{count}**")
                    col2.markdown(f"**{name}**")
                    col3.code(certificate_id, language=None)

                    # Determine approval status
                    is_approved = False
                    try:
                        is_approved = contract.functions.isCertificateApproved(certificate_id).call()
                    except:
                        is_approved = False

                    if not is_approved:
                        # Check if rejected
                        rejection_info = None
                        rejections = get_rejections_for_institute(st.session_state.user_email)
                        for rid, rinfo in rejections.items():
                            if rinfo.get("cert_info", {}).get("ipfs_hash") == ipfs_hash:
                                rejection_info = rinfo
                                rejection_cert_id = rid
                                break

                        if rejection_info:
                            col4.markdown("❌ **Rejected**")
                            with st.container():
                                st.error(f"**Admin Remarks:** {rejection_info['remarks']}")
                                ci = rejection_info.get("cert_info", {})
                                st.markdown(
                                    f"**Original Details** — Name: {ci.get('candidate_name', '')}, "
                                    f"Course: {ci.get('course_name', '')}, Org: {ci.get('org_name', '')}, "
                                    f"Grade: {ci.get('grade', '')}"
                                )
                                st.caption(f"Rejected on: {rejection_info.get('rejected_at', '')[:19]}")
                                reapply_col1, reapply_col2 = st.columns(2)
                                with reapply_col1:
                                    if st.button("🔄 Reapply with Edits", key=f"reapply_{ipfs_hash}", type="primary"):
                                        st.session_state["reapply_data"] = ci
                                        st.session_state["reapply_cert_id"] = rejection_cert_id
                                        st.session_state["selected_page"] = "Generate Certificate"
                                        st.rerun()
                                with reapply_col2:
                                    if st.button("🗑️ Dismiss & Delete", key=f"dismiss_{ipfs_hash}"):
                                        remove_rejection(rejection_cert_id)
                                        delete_pinata_file(ipfs_hash)
                                        clear_face_profile(rejection_cert_id)
                                        st.success("✅ Rejected certificate dismissed and cleaned up.")
                                        st.rerun()
                        else:
                            col4.markdown("⏳ **Pending**")
                    else:
                        try:
                            is_revoked = contract.functions.isRevoked(certificate_id).call()
                            is_pending_rev = contract.functions.isPendingRevocation(certificate_id).call()
                        except:
                            is_revoked = False
                            is_pending_rev = False

                        if is_revoked:
                            col4.markdown("🚫 **Revoked**")
                        elif is_pending_rev:
                            col4.markdown("⏳ **Rev. Pending**")
                        else:
                            rev_rejection = get_revocation_rejection(certificate_id)
                            if rev_rejection:
                                col4.markdown("❌ **Rev. Rejected**")
                                st.warning(f"**Revocation Rejection Remarks:** {rev_rejection.get('remarks', '')}")
                                st.caption(f"Rejected on: {rev_rejection.get('rejected_at', '')[:19]}")
                            if col4.button("Revoke", key=f"rev_{ipfs_hash}"):
                                try:
                                    institute_signer = get_institute_signer(st.session_state.user_email)
                                    send_tx(
                                        contract.functions.proposeRevocation(certificate_id),
                                        institute_signer,
                                    )
                                    remove_revocation_rejection(certificate_id)
                                    st.success("✅ Revocation request submitted!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Failed: {str(e)}")

                    # Download options
                    dl_key = f"dl_pdf_{ipfs_hash}"
                    if col5.button("📥 Get PDF", key=f"get_{ipfs_hash}"):
                        try:
                            import requests
                            enc_key = get_encryption_key(certificate_id, st.session_state.user_email, "institute")
                            if enc_key:
                                resp = requests.get(link, timeout=60)
                                if resp.status_code == 200:
                                    pdf_bytes = decrypt_file(resp.content, enc_key)
                                    st.session_state[dl_key] = pdf_bytes
                                else:
                                    st.warning("Could not fetch from IPFS.")
                            else:
                                st.warning("No encryption key found.")
                        except Exception as e:
                            st.error(f"Download failed: {str(e)}")

                    if dl_key in st.session_state:
                        pdf_name = name.replace('.enc', '.pdf') if name.endswith('.enc') else name
                        st.download_button(
                            "💾 Download PDF",
                            st.session_state[dl_key],
                            file_name=pdf_name,
                            mime="application/pdf",
                            key=f"dl_btn_{ipfs_hash}"
                        )
                        st.markdown(f"[📥 Download Encrypted File]({link})")

                    # Downloadable QR code (encodes the certificate_id).
                    st.download_button(
                        "🔳 Download QR",
                        data=make_qr_png_bytes(certificate_id),
                        file_name=f"{certificate_id[:12]}_qr.png",
                        mime="image/png",
                        key=f"qr_btn_{ipfs_hash}",
                    )

                    st.markdown("---")
                    count += 1

        # ===== BATCH CERTIFICATES =====
        if batch_groups:
            st.markdown("### 📦 Batch Certificates")
            for batch_id, batch_certs in batch_groups.items():
                # Determine batch status
                batch_status = "unknown"
                batch_is_approved = False
                batch_rejection_info = None
                try:
                    batch_data = contract.functions.getBatch(int(batch_id)).call()
                    if batch_data[2] == 0 and batch_data[4] == 0:
                        batch_rejection_info = get_batch_rejection(batch_id)
                        batch_status = "rejected"
                    elif batch_data[3]:
                        batch_status = "approved"
                        batch_is_approved = True
                    else:
                        batch_status = "pending"
                except:
                    batch_rejection_info = get_batch_rejection(batch_id)
                    batch_status = "rejected" if batch_rejection_info else "unknown"

                # Batch header
                status_icon = {"approved": "✅", "pending": "⏳", "rejected": "❌", "unknown": "❓"}
                status_label = {"approved": "Approved", "pending": "Pending", "rejected": "Rejected", "unknown": "Unknown"}

                with st.expander(
                    f"📦 Batch #{batch_id} — {len(batch_certs)} certificate(s) — {status_icon.get(batch_status, '')} {status_label.get(batch_status, '')}",
                    expanded=False
                ):
                    # Show rejection remarks if batch was rejected
                    if batch_status == "rejected" and batch_rejection_info:
                        st.error(f"**Admin Remarks:** {batch_rejection_info['remarks']}")
                        st.caption(f"Rejected on: {batch_rejection_info.get('rejected_at', '')[:19]}")

                    batch_zip_key = f"batch_zip_{batch_id}"
                    batch_zip_name_key = f"batch_zip_name_{batch_id}"
                    if st.button("📦 Prepare Batch ZIP", key=f"prepare_batch_zip_{batch_id}"):
                        zip_certs = [
                            {
                                "certificate_id": cert_id,
                                "candidate_name": cert_meta.get("candidate_name", ""),
                                "ipfs_hash": file_info.get("ipfs_pin_hash", ""),
                            }
                            for file_info, cert_id, cert_meta in batch_certs
                        ]
                        with st.spinner(f"Preparing Batch #{batch_id} ZIP..."):
                            zip_bytes, added_count, zip_name = _build_certificates_zip(
                                zip_certs,
                                zip_title=f"batch_{batch_id}_certificates",
                            )
                        st.session_state[batch_zip_key] = zip_bytes
                        st.session_state[batch_zip_name_key] = zip_name
                        st.success(f"Prepared ZIP with {added_count} certificate PDF(s) and QR code(s).")

                    if batch_zip_key in st.session_state:
                        st.download_button(
                            "💾 Download Batch ZIP",
                            data=st.session_state[batch_zip_key],
                            file_name=st.session_state.get(batch_zip_name_key, f"batch_{batch_id}_certificates.zip"),
                            mime="application/zip",
                            key=f"download_batch_zip_{batch_id}",
                        )

                    # Table of certificates in this batch
                    for cert_idx, (f, certificate_id, cert_meta) in enumerate(batch_certs):
                        name = f['metadata'].get('name', 'Unnamed')
                        ipfs_hash = f['ipfs_pin_hash']
                        link = f"https://gateway.pinata.cloud/ipfs/{ipfs_hash}"
                        cand_name = cert_meta.get("candidate_name", "")
                        course = cert_meta.get("course_name", "")
                        grade_val = cert_meta.get("grade", "")

                        c1, c2, c3, c4, c5 = st.columns([1, 3, 3, 2, 2])
                        c1.markdown(f"**{cert_idx + 1}**")
                        c2.markdown(f"**{cand_name}**")
                        c3.markdown(f"{course} {'(' + grade_val + ')' if grade_val else ''}")

                        # Per-cert status within the batch
                        if batch_status == "rejected":
                            c4.markdown("❌ Rejected")
                        elif batch_status == "pending":
                            c4.markdown("⏳ Pending")
                        elif batch_status == "approved":
                            try:
                                is_revoked = contract.functions.isRevoked(certificate_id).call()
                                is_pending_rev = contract.functions.isPendingRevocation(certificate_id).call()
                            except:
                                is_revoked = False
                                is_pending_rev = False

                            if is_revoked:
                                c4.markdown("🚫 Revoked")
                            elif is_pending_rev:
                                c4.markdown("⏳ Rev. Pending")
                            else:
                                rev_rejection = get_revocation_rejection(certificate_id)
                                if rev_rejection:
                                    c4.markdown("❌ Rev. Rejected")
                                    st.warning(f"**Revocation Rejection Remarks:** {rev_rejection.get('remarks', '')}")
                                    st.caption(f"Rejected on: {rev_rejection.get('rejected_at', '')[:19]}")
                                if c4.button("Revoke", key=f"rev_batch_{batch_id}_{cert_idx}"):
                                    try:
                                        institute_signer = get_institute_signer(st.session_state.user_email)
                                        send_tx(
                                            contract.functions.proposeRevocationBatchCert(
                                                certificate_id,
                                                st.session_state.user_email,
                                            ),
                                            institute_signer,
                                        )
                                        remove_revocation_rejection(certificate_id)
                                        st.success("✅ Revocation request submitted!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Failed: {str(e)}")

                        # Download
                        dl_key = f"dl_pdf_{ipfs_hash}"
                        if c5.button("📥 Get PDF", key=f"get_batch_{batch_id}_{cert_idx}"):
                            try:
                                import requests
                                enc_key = get_encryption_key(certificate_id, st.session_state.user_email, "institute")
                                if enc_key:
                                    resp = requests.get(link, timeout=60)
                                    if resp.status_code == 200:
                                        pdf_bytes = decrypt_file(resp.content, enc_key)
                                        st.session_state[dl_key] = pdf_bytes
                                    else:
                                        st.warning("Could not fetch from IPFS.")
                                else:
                                    st.warning("No encryption key found.")
                            except Exception as e:
                                st.error(f"Download failed: {str(e)}")

                        if dl_key in st.session_state:
                            pdf_name = name.replace('.enc', '.pdf') if name.endswith('.enc') else name
                            st.download_button(
                                "💾 Download PDF",
                                st.session_state[dl_key],
                                file_name=pdf_name,
                                mime="application/pdf",
                                key=f"dl_btn_batch_{batch_id}_{cert_idx}"
                            )
                            st.markdown(f"[📥 Download Encrypted File]({link})")

                        # Downloadable QR code (encodes the certificate_id).
                        st.download_button(
                            "🔳 Download QR",
                            data=make_qr_png_bytes(certificate_id),
                            file_name=f"{certificate_id[:12]}_qr.png",
                            mime="image/png",
                            key=f"qr_btn_batch_{batch_id}_{cert_idx}",
                        )

                        # Full certificate ID for copy/paste into the Verify / View flows.
                        st.caption("Certificate ID")
                        st.code(certificate_id, language=None)

                        st.markdown("---")

                count += 1

        # ===== UNKNOWN FILES (not on blockchain) =====
        if unknown_files:
            st.markdown("### ❓ Unlinked Files")
            for f in unknown_files:
                name = f['metadata'].get('name', 'Unnamed')
                ipfs_hash = f['ipfs_pin_hash']

                # Check if this was a rejected individual cert
                rejection_info = None
                rejections = get_rejections_for_institute(st.session_state.user_email)
                for rid, rinfo in rejections.items():
                    if rinfo.get("cert_info", {}).get("ipfs_hash") == ipfs_hash:
                        rejection_info = rinfo
                        rejection_cert_id = rid
                        break

                with st.container():
                    col1, col2, col3, col4 = st.columns([1, 3, 4, 2])
                    col1.markdown(f"**{count}**")
                    col2.markdown(f"**{name}**")

                    if rejection_info:
                        col3.markdown("❌ **Rejected**")
                        with st.container():
                            st.error(f"**Admin Remarks:** {rejection_info['remarks']}")
                            ci = rejection_info.get("cert_info", {})
                            st.markdown(
                                f"**Original Details** — Name: {ci.get('candidate_name', '')}, "
                                f"Course: {ci.get('course_name', '')}, Org: {ci.get('org_name', '')}, "
                                f"Grade: {ci.get('grade', '')}"
                            )
                            st.caption(f"Rejected on: {rejection_info.get('rejected_at', '')[:19]}")
                            reapply_col1, reapply_col2 = st.columns(2)
                            with reapply_col1:
                                if st.button("🔄 Reapply with Edits", key=f"reapply_{ipfs_hash}", type="primary"):
                                    st.session_state["reapply_data"] = ci
                                    st.session_state["reapply_cert_id"] = rejection_cert_id
                                    st.session_state["selected_page"] = "Generate Certificate"
                                    st.rerun()
                            with reapply_col2:
                                if st.button("🗑️ Dismiss & Delete", key=f"dismiss_{ipfs_hash}"):
                                    remove_rejection(rejection_cert_id)
                                    delete_pinata_file(ipfs_hash)
                                    clear_face_profile(rejection_cert_id)
                                    st.success("✅ Rejected certificate dismissed and cleaned up.")
                                    st.rerun()
                    else:
                        col3.markdown("_Not on blockchain_")
                        if col4.button("Delete from IPFS", key=ipfs_hash):
                            if delete_pinata_file(ipfs_hash):
                                st.success("✅ File deleted from IPFS!")
                                st.rerun()
                            else:
                                st.error("Failed to delete file from Pinata.")

                    st.markdown("---")
                    count += 1

# --- Certificate Generation ---
elif selected == "Generate Certificate":
    next_uid = get_next_uid()

    # Pre-fill from reapply data if available (keep in session until successful submit)
    reapply = st.session_state.get("reapply_data", None)
    reapply_cert_id = st.session_state.get("reapply_cert_id", None)
    if reapply:
        st.info("📝 **Reapplying a rejected certificate.** Edit the details below and resubmit.")

    st.markdown("#### Fill the details to generate certificate")
    uid = st.text_input(label="UID", value=next_uid, disabled=True)
    candidate_name = st.text_input(label="Candidate Name", value=reapply.get("candidate_name", "") if reapply else "")
    course_name = st.text_input(label="Course Name", value=reapply.get("course_name", "") if reapply else "")
    org_name = st.text_input(label="Issuing Organization", value=reapply.get("org_name", "") if reapply else "")
    grade = st.text_input(label="Grade", placeholder="e.g., A+, B, First Class", value=reapply.get("grade", "") if reapply else "")

    st.markdown("##### 📸 Candidate Face Photo (required)")
    st.caption("A clear front-facing photo. Used for biometric verification by employers.")
    face_camera = st.camera_input(
        "Capture candidate face",
        key="single_cert_face_camera",
    )
    face_upload = st.file_uploader(
        "Or upload candidate face photo",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=False,
        key="single_cert_face_upload",
    )
    face_image = face_upload if face_upload is not None else face_camera

    submit = st.button("Generate", type="primary")

    if submit:
        if not all([uid, candidate_name, course_name, org_name, grade]):
            st.warning("Please fill all fields.")
        elif face_image is None:
            st.warning("Please upload or capture a candidate face photo to bind to this certificate.")
        else:
            # Pre-flight: ensure the photo actually contains a usable face
            # before we burn an on-chain transaction or upload to IPFS.
            face_ok, face_err = detect_face(face_image)
            if not face_ok:
                st.error(f"❌ Face check failed: {face_err}")
                st.stop()
            with st.spinner("Generating certificate..."):
                pdf_file_path = f"{uid}_{candidate_name.strip().replace(' ', '_').lower()}.pdf"
                institute_logo_path = "../assets/logo.jpg"

                # Compute cert_id BEFORE PDF generation so it can be embedded as a QR.
                salt = os.urandom(16).hex()
                data = f"{salt}{uid}{candidate_name}{course_name}{org_name}{grade}".encode("utf-8")
                certificate_id = hashlib.sha256(data).hexdigest()

                generate_certificate(pdf_file_path, uid, candidate_name, course_name, org_name, institute_logo_path, grade, certificate_id=certificate_id)

                # Encrypt the PDF before uploading
                encryption_key = generate_key()
                encrypted_bytes = encrypt_file(pdf_file_path, encryption_key)
                encrypted_filename = f"{os.path.splitext(pdf_file_path)[0]}.enc"

                ipfs_hash = upload_bytes_to_pinata(encrypted_bytes, encrypted_filename, st.session_state.user_email)
                os.remove(pdf_file_path)

                if ipfs_hash:
                    # Create certificate data for digital signature
                    certificate_data = {
                        "uid": uid,
                        "candidate_name": candidate_name,
                        "course_name": course_name,
                        "org_name": org_name,
                        "ipfs_hash": ipfs_hash,
                        "certificate_id": certificate_id,
                        "salt": salt,
                        "grade": grade
                    }

                    # Generate digital signature
                    digital_signature = crypto_auth.sign_certificate_data(
                        st.session_state.user_email, 
                        certificate_data
                    )

                    # Store on Blockchain
                    try:
                        institute_signer = get_institute_signer(st.session_state.user_email)
                        if not institute_signer:
                            st.error("❌ No bound signer for this institute. Re-register.")
                            st.stop()
                        send_tx(
                            contract.functions.proposeCertificate(
                                certificate_id,
                                uid,
                                candidate_name,
                                course_name,
                                org_name,
                                ipfs_hash,
                                st.session_state.user_email,
                                digital_signature,
                                salt,
                                grade,
                            ),
                            institute_signer,
                        )
                        uid_created(next_uid)

                        # Save encryption key with access control
                        save_encryption_key(certificate_id, encryption_key, st.session_state.user_email)

                        # Add to Bloom Filter for fast verification lookups
                        bloom_add(certificate_id)

                        # Bind candidate face to this certificate (mandatory at issuance)
                        face_result = enroll_face_for_cert(
                            certificate_id,
                            face_image,
                            owner_name=candidate_name,
                            institute_email=st.session_state.user_email,
                        )
                        if face_result["success"]:
                            # Anchor the face profile hash on-chain so the verifier
                            # can detect any post-issuance tampering of the
                            # off-chain face_profiles store.
                            face_digest = hash_face_profile(certificate_id)
                            if face_digest is not None:
                                try:
                                    send_tx(
                                        contract.functions.setCertificateFaceHash(
                                            certificate_id, face_digest
                                        ),
                                        institute_signer,
                                    )
                                except Exception as exc:
                                    st.warning(f"⚠️ Could not anchor face hash on-chain: {exc}")
                            st.success(
                                f"🧑‍💼 Face profile bound to certificate ({face_result['sample_count']} sample)."
                            )
                        else:
                            st.warning(
                                "⚠️ Face enrollment failed: "
                                + " | ".join(face_result.get("errors", ["unknown error"]))
                                + " You can re-enroll from the Face ID Enrollment page."
                            )

                        # Clean up old rejection record if this is a reapply
                        if reapply_cert_id:
                            remove_rejection(reapply_cert_id)
                            old_ipfs = reapply.get("ipfs_hash") if reapply else None
                            if old_ipfs:
                                delete_pinata_file(old_ipfs)
                            clear_face_profile(reapply_cert_id)
                            st.session_state.pop("reapply_data", None)
                            st.session_state.pop("reapply_cert_id", None)

                        st.success(f"✅ Certificate proposed with digital signature and encryption!")
                        st.success(f"Certificate ID: `{certificate_id}`")
                        st.info("⏳ Certificate is pending admin approval. It will be active once approved.")

                        # Fetch encrypted PDF from IPFS, decrypt, and display
                        import requests
                        pinata_gateway_base_url = 'https://gateway.pinata.cloud/ipfs'
                        content_url = f"{pinata_gateway_base_url}/{ipfs_hash}"
                        response = requests.get(content_url)
                        if response.status_code == 200:
                            encrypted_pdf = response.content
                            pdf_bytes = decrypt_file(encrypted_pdf, encryption_key)
                            import base64
                            base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="700" height="1000" type="application/pdf"></iframe>'
                            st.markdown(pdf_display, unsafe_allow_html=True)
                            st.download_button(
                                label="📥 Download Certificate PDF",
                                data=pdf_bytes,
                                file_name=pdf_file_path,
                                mime="application/pdf"
                            )
                            st.download_button(
                                label="🔳 Download Certificate QR",
                                data=make_qr_png_bytes(certificate_id),
                                file_name=f"{certificate_id[:12]}_qr.png",
                                mime="image/png",
                                key=f"generated_qr_{certificate_id}",
                            )
                        else:
                            st.warning("Could not fetch the certificate PDF from IPFS.")
                    except Exception as e:
                        st.error(f"⚠️ Blockchain transaction failed: {str(e)}")

# --- Face ID Enrollment ---
elif selected == "Face ID Enrollment":
    st.markdown("### 🧑‍💼 Face ID Enrollment")
    st.info("Bind a live face profile to a certificate so it must be matched before the certificate can be viewed or verified.")

    prefill_cert_id = st.session_state.get("face_enroll_cert_id", "")
    with st.form("Face-ID-Lookup"):
        certificate_id_input = st.text_input("Certificate ID", value=prefill_cert_id)
        load_clicked = st.form_submit_button("Load Certificate")

    # Load + cache the cert context in session_state so subsequent reruns
    # (triggered by camera_input / file_uploader / Save button) can still see it.
    if load_clicked:
        cid = certificate_id_input.strip()
        if not cid:
            st.warning("Please enter a certificate ID.")
            st.session_state.pop("face_enroll_context", None)
        else:
            certificate_context = None
            try:
                cert_data = contract.functions.getCertificate(cid).call()
                if cert_data[5] != st.session_state.user_email:
                    st.error("❌ This certificate was not issued by your institute.")
                    st.session_state.pop("face_enroll_context", None)
                    st.stop()

                certificate_context = {
                    "type": "individual",
                    "certificate_id": cid,
                    "candidate_name": cert_data[1],
                    "course_name": cert_data[2],
                    "org_name": cert_data[3],
                    "institute_email": cert_data[5],
                }
            except Exception:
                batch_id, batch_cert_data = find_certificate_batch(cid)
                if batch_id is not None:
                    try:
                        batch_data = contract.functions.getBatch(int(batch_id)).call()
                        if batch_data[1] != st.session_state.user_email:
                            st.error("❌ This batch certificate was not issued by your institute.")
                            st.session_state.pop("face_enroll_context", None)
                            st.stop()

                        certificate_context = {
                            "type": "batch",
                            "batch_id": batch_id,
                            "certificate_id": cid,
                            "candidate_name": batch_cert_data.get("candidate_name", ""),
                            "course_name": batch_cert_data.get("course_name", ""),
                            "org_name": batch_cert_data.get("org_name", ""),
                            "institute_email": batch_data[1],
                        }
                    except Exception as e:
                        st.error(f"❌ Could not load batch certificate details: {str(e)}")
                        st.session_state.pop("face_enroll_context", None)
                        st.stop()
                else:
                    st.error("❌ Certificate not found on blockchain or in the batch store.")
                    st.session_state.pop("face_enroll_context", None)
                    st.stop()

            if certificate_context is not None:
                st.session_state["face_enroll_context"] = certificate_context
                st.session_state["face_enroll_cert_id"] = cid

    # Render capture/save UI from cached context (survives reruns).
    certificate_context = st.session_state.get("face_enroll_context")
    if certificate_context:
        certificate_id = certificate_context["certificate_id"]

        profile = get_face_profile(certificate_id)
        if profile:
            st.warning(
                f"An existing face profile is already stored for this certificate with {profile.get('sample_count', 0)} sample(s). Saving again will replace it."
            )

        st.markdown("#### Certificate Details")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Candidate Name:** {certificate_context['candidate_name']}")
            st.markdown(f"**Course:** {certificate_context['course_name']}")
        with col2:
            st.markdown(f"**Organization:** {certificate_context['org_name']}")
            if certificate_context.get("type") == "batch":
                st.markdown(f"**Batch ID:** {certificate_context.get('batch_id')}")

        st.markdown("#### Capture Face Samples")
        st.caption("Recommended: capture at least one clear image with the face centered. Multiple samples improve matching quality.")
        camera_sample = st.camera_input("Capture owner face", key=f"face_enroll_camera_{certificate_id}")
        uploaded_samples = st.file_uploader(
            "Optional additional face images",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key=f"face_enroll_upload_{certificate_id}",
        )

        save_clicked = st.button("💾 Save Face Profile", key=f"save_face_{certificate_id}", type="primary")
        if save_clicked:
            face_inputs = []
            if camera_sample is not None:
                face_inputs.append(camera_sample)
            if uploaded_samples:
                face_inputs.extend(uploaded_samples)

            if not face_inputs:
                st.warning("Please capture or upload at least one face image.")
            else:
                result = save_face_samples(
                    certificate_id,
                    face_inputs,
                    owner_name=certificate_context["candidate_name"],
                    institute_email=certificate_context["institute_email"],
                )
                if result["success"]:
                    st.success(f"✅ Face profile saved with {result['sample_count']} sample(s).")
                    if result.get("errors"):
                        st.warning("Some samples were skipped: " + " | ".join(result["errors"]))
                    st.session_state["face_enroll_owner_name"] = certificate_context["candidate_name"]
                else:
                    st.error("❌ Face enrollment failed.")
                    if result.get("errors"):
                        st.error(" | ".join(result["errors"]))

        if st.button("Clear loaded certificate", key=f"clear_face_ctx_{certificate_id}"):
            st.session_state.pop("face_enroll_context", None)
            st.rerun()

# --- Certificate Viewing ---
elif selected == "View Certificates":
    with st.form("View-Certificate"):
        st.markdown("#### Enter your Certificate ID to view it")
        certificate_id = st.text_input("Certificate ID", value=st.session_state.get("view_certificate_id", ""))
        submit = st.form_submit_button("View")

    if submit:
        if not certificate_id.strip():
            st.warning("Please enter a Certificate ID.")
            st.session_state.pop("view_certificate_id", None)
        else:
            st.session_state["view_certificate_id"] = certificate_id.strip()

    certificate_id_to_view = st.session_state.get("view_certificate_id")
    if certificate_id_to_view:
        with st.spinner("Fetching certificate..."):
            try:
                view_certificate(certificate_id_to_view, st.session_state.user_email, user_role="institute")
            except Exception as e:
                print(e)
                st.error("❌ Invalid Certificate ID or blockchain error.")

# --- Bulk Generate ---
elif selected == "Bulk Generate":
    st.markdown("#### 📦 Bulk Certificate Generation")
    st.info("Upload a CSV file with columns: **Number, Name, Course, Organization, Grade**")
    st.markdown("The Number column is just for CSV ordering and will be ignored. UIDs are auto-generated.")

    uploaded_csv = st.file_uploader("Upload CSV", type=["csv"])

    st.markdown("##### 📸 Candidate Face Photos (required)")
    st.caption(
        "Upload a ZIP of face images. Image filename (without extension) must match either the **Number** column "
        "or the candidate **Name** (case-insensitive, spaces → underscores). Rows without a matching image will be skipped."
    )
    uploaded_face_zip = st.file_uploader("Upload Face Images (ZIP)", type=["zip"], key="bulk_face_zip")

    if uploaded_csv:
        import pandas as pd
        try:
            df = pd.read_csv(uploaded_csv)

            # Validate columns (expect at least 5 columns)
            if len(df.columns) < 5:
                st.error("❌ CSV must have at least 5 columns: Number, Name, Course, Organization, Grade")
                st.stop()

            # Use positional columns: 0=number(ignore), 1=name, 2=course, 3=organization, 4=grade
            df.columns = ["number", "name", "course", "organization", "grade"] + list(df.columns[5:])

            st.success(f"✅ Loaded {len(df)} records from CSV")

            # Preview the data
            preview_df = df[["name", "course", "organization", "grade"]].copy()
            preview_df.index = range(1, len(preview_df) + 1)
            st.dataframe(preview_df, use_container_width=True)

            if st.button("Validate Inputs", type="secondary"):
                # Build the face image map from the ZIP and pre-flight every
                # row: detect a usable face in the matched image. The user
                # then sees a full report and must explicitly confirm before
                # any blockchain transaction is sent.
                if uploaded_face_zip is None:
                    st.error("❌ Please upload a ZIP of candidate face photos before validating.")
                    st.stop()

                face_image_map = {}
                import zipfile as _zip
                from io import BytesIO as _BytesIO
                try:
                    with _zip.ZipFile(_BytesIO(uploaded_face_zip.getvalue())) as zf:
                        for member in zf.namelist():
                            if member.endswith("/"):
                                continue
                            ext = os.path.splitext(member)[1].lower()
                            if ext not in (".png", ".jpg", ".jpeg"):
                                continue
                            stem = os.path.splitext(os.path.basename(member))[0].strip().lower()
                            if not stem:
                                continue
                            face_image_map[stem] = zf.read(member)
                except Exception as exc:
                    st.error(f"❌ Could not read face ZIP: {exc}")
                    st.stop()

                validated_rows = []      # rows ready to issue
                problem_rows = []        # rows that will be skipped
                progress = st.progress(0.0)
                status = st.empty()
                for idx, row in df.iterrows():
                    candidate_name = str(row["name"]).strip()
                    course_name = str(row["course"]).strip()
                    org_name = str(row["organization"]).strip()
                    grade = str(row["grade"]).strip()
                    row_number = str(row["number"]).strip().lower()
                    name_key = candidate_name.lower().replace(" ", "_")

                    status.text(f"Validating {idx + 1}/{len(df)}: {candidate_name or '(unnamed)'}")
                    progress.progress((idx + 1) / max(len(df), 1))

                    # Required fields present?
                    if not all([candidate_name, course_name, org_name, grade]):
                        problem_rows.append({
                            "row": idx + 1,
                            "candidate_name": candidate_name or "(unnamed)",
                            "issue": "Missing required field(s) (name/course/organization/grade)",
                        })
                        continue

                    face_bytes = (
                        face_image_map.get(row_number)
                        or face_image_map.get(name_key)
                        or face_image_map.get(candidate_name.lower())
                    )
                    if face_bytes is None:
                        problem_rows.append({
                            "row": idx + 1,
                            "candidate_name": candidate_name,
                            "issue": (
                                f"No face image found in ZIP "
                                f"(looked for '{row_number}.*' or '{name_key}.*')"
                            ),
                        })
                        continue

                    ok, msg = detect_face(face_bytes)
                    if not ok:
                        problem_rows.append({
                            "row": idx + 1,
                            "candidate_name": candidate_name,
                            "issue": f"Face check failed: {msg}",
                        })
                        continue

                    validated_rows.append({
                        "row": idx + 1,
                        "candidate_name": candidate_name,
                        "course_name": course_name,
                        "org_name": org_name,
                        "grade": grade,
                        "face_bytes": face_bytes,
                    })

                progress.empty()
                status.empty()

                st.session_state["bulk_validated_rows"] = validated_rows
                st.session_state["bulk_problem_rows"] = problem_rows
                st.session_state["bulk_total_rows"] = int(len(df))
                st.session_state.pop("bulk_confirm", None)

            # Render validation summary + confirmation gate (persists across reruns).
            if "bulk_validated_rows" in st.session_state:
                validated_rows = st.session_state["bulk_validated_rows"]
                problem_rows = st.session_state["bulk_problem_rows"]
                total_rows = st.session_state["bulk_total_rows"]

                st.markdown("---")
                st.markdown("#### ✅ Validation Summary")
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Total rows", total_rows)
                col_b.metric("Ready to issue", len(validated_rows))
                col_c.metric("Will be skipped", len(problem_rows), delta_color="inverse")

                if problem_rows:
                    st.warning(
                        f"⚠️ {len(problem_rows)} of {total_rows} rows have problems and will be **skipped** if you proceed."
                    )
                    import pandas as _pd
                    st.dataframe(
                        _pd.DataFrame(problem_rows),
                        use_container_width=True,
                        hide_index=True,
                    )

                if not validated_rows:
                    st.error("❌ No rows are valid. Fix the issues above and re-validate before generating.")
                    proceed = False
                else:
                    if problem_rows:
                        confirmed = st.checkbox(
                            f"I understand that {len(problem_rows)} row(s) will be skipped, "
                            f"and I want to issue certificates for the remaining {len(validated_rows)}.",
                            key="bulk_confirm",
                        )
                    else:
                        st.success("All rows passed validation. Ready to generate.")
                        confirmed = True

                    proceed = st.button(
                        f"🚀 Generate {len(validated_rows)} Certificate(s)",
                        type="primary",
                        disabled=not confirmed,
                        key="bulk_generate_now",
                    )

                if validated_rows and proceed:
                    with st.spinner(f"Generating {len(validated_rows)} certificates..."):
                        certificates = []
                        leaves = []
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        for i, vrow in enumerate(validated_rows):
                            candidate_name = vrow["candidate_name"]
                            course_name = vrow["course_name"]
                            org_name = vrow["org_name"]
                            grade = vrow["grade"]
                            face_bytes = vrow["face_bytes"]

                            uid = get_next_uid()
                            status_text.text(f"Processing {i + 1}/{len(validated_rows)}: {candidate_name}")

                            pdf_file_path = f"{uid}_{candidate_name.strip().replace(' ', '_').lower()}.pdf"
                            institute_logo_path = "../assets/logo.jpg"

                            # Compute cert_id BEFORE PDF generation so the QR can be embedded.
                            salt = os.urandom(16).hex()
                            certificate_id = hashlib.sha256(
                                f"{salt}{uid}{candidate_name}{course_name}{org_name}{grade}".encode("utf-8")
                            ).hexdigest()

                            generate_certificate(pdf_file_path, uid, candidate_name, course_name, org_name, institute_logo_path, grade, certificate_id=certificate_id)

                            encryption_key = generate_key()
                            encrypted_bytes = encrypt_file(pdf_file_path, encryption_key)
                            encrypted_filename = f"{os.path.splitext(pdf_file_path)[0]}.enc"
                            ipfs_hash = upload_bytes_to_pinata(encrypted_bytes, encrypted_filename, st.session_state.user_email)
                            os.remove(pdf_file_path)

                            if not ipfs_hash:
                                st.error(f"❌ Failed to upload certificate for {candidate_name}")
                                continue

                            save_encryption_key(certificate_id, encryption_key, st.session_state.user_email)

                            # Enroll the face FIRST so we can hash the embedding
                            # and bake the digest into the Merkle leaf, anchoring
                            # the off-chain face profile to the on-chain root.
                            face_result = enroll_face_for_cert(
                                certificate_id,
                                face_bytes,
                                owner_name=candidate_name,
                                institute_email=st.session_state.user_email,
                            )
                            if not face_result["success"]:
                                st.warning(
                                    f"⚠️ Face enrollment failed for {candidate_name}: "
                                    + " | ".join(face_result.get("errors", ["unknown"]))
                                )
                                face_hash_hex = ""
                            else:
                                face_digest = hash_face_profile(certificate_id)
                                face_hash_hex = face_digest.hex() if face_digest else ""

                            leaf_hash = compute_leaf(
                                salt, uid, candidate_name, course_name, org_name, grade,
                                face_hash=face_hash_hex,
                            )

                            uid_created(uid)

                            certificates.append({
                                "certificate_id": certificate_id,
                                "leaf_hash": leaf_hash,
                                "uid": uid,
                                "candidate_name": candidate_name,
                                "course_name": course_name,
                                "org_name": org_name,
                                "salt": salt,
                                "grade": grade,
                                "ipfs_hash": ipfs_hash,
                                "face_hash": face_hash_hex,
                            })
                            leaves.append(leaf_hash)

                            progress_bar.progress((i + 1) / len(validated_rows))

                        if not certificates:
                            st.error("❌ No certificates were generated.")
                            st.stop()

                        # Build Merkle tree
                        status_text.text("Building Merkle tree...")
                        merkle_root, tree_layers = build_merkle_tree(leaves)
                        root_bytes = bytes.fromhex(merkle_root)

                        status_text.text("Storing Merkle root on blockchain...")
                        try:
                            institute_signer = get_institute_signer(st.session_state.user_email)
                            send_tx(
                                contract.functions.proposeBatch(
                                    root_bytes,
                                    st.session_state.user_email,
                                    len(certificates),
                                ),
                                institute_signer,
                            )

                            batch_id = contract.functions.getBatchCount().call()
                            save_batch_proofs(batch_id, certificates, tree_layers, merkle_root)

                            for cert in certificates:
                                bloom_add(cert["certificate_id"])

                            progress_bar.progress(1.0)
                            status_text.text("")

                            st.success(f"🎉 Batch of {len(certificates)} certificates proposed!")
                            st.success(f"Batch ID: `{batch_id}`")
                            st.info(f"Merkle Root: `{merkle_root}`")
                            st.info("⏳ Batch is pending admin approval.")

                            # Show certificate IDs as a copy-friendly table
                            st.markdown("#### Generated Certificate IDs")
                            import pandas as _pd
                            id_df = _pd.DataFrame([
                                {"Candidate": c["candidate_name"], "UID": c["uid"], "Certificate ID": c["certificate_id"]}
                                for c in certificates
                            ])
                            st.dataframe(id_df, use_container_width=True, hide_index=True)

                            st.session_state["bulk_generated_certs"] = certificates
                            with st.spinner("Preparing ZIP with PDFs and QR codes..."):
                                zip_bytes, added_count, zip_name = _build_certificates_zip(
                                    certificates,
                                    zip_title=f"batch_{batch_id}_certificates",
                                )
                            st.download_button(
                                "💾 Download All as ZIP",
                                data=zip_bytes,
                                file_name=zip_name,
                                mime="application/zip",
                                key=f"download_bulk_zip_{batch_id}",
                            )
                            st.caption(f"ZIP includes {added_count} certificate PDF(s) and QR code(s).")

                            # Clear validation cache so the user must re-validate for the next batch.
                            for k in ("bulk_validated_rows", "bulk_problem_rows", "bulk_total_rows", "bulk_confirm"):
                                st.session_state.pop(k, None)

                        except Exception as e:
                            st.error(f"❌ Blockchain transaction failed: {str(e)}")

        except Exception as e:
            st.error(f"❌ Error reading CSV: {str(e)}")

