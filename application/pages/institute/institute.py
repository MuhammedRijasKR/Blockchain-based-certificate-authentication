import hashlib
import os
import json

import streamlit as st
from connection import contract, w3
from dotenv import load_dotenv
from utils.auth import AuthManager
from utils.cert_utils import generate_certificate, get_certificate_id_ipfs_hash
from utils.pinata_utils import upload_to_pinata, upload_bytes_to_pinata, delete_pinata_file, get_pinata_files
from utils.streamlit_utils import hide_sidebar
from utils.streamlit_utils import view_certificate, get_next_uid, uid_created
from utils.crypto_utils import DigitalCertificateAuth
from utils.encryption_utils import generate_key, encrypt_file, save_encryption_key, get_encryption_key, decrypt_file

hide_sidebar()
auth = AuthManager()
crypto_auth = DigitalCertificateAuth()

auth.require_auth(allowed_roles=("institute",))

load_dotenv()

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

selected = st.selectbox("Select an option", options, label_visibility="collapsed")

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
                    
                    # Register institute on blockchain (pending verification)
                    contract.functions.registerInstitute(
                        institute_email,
                        institute_name,
                        public_key
                    ).transact({'from': w3.eth.accounts[0]})
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
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Institute Name:** {name}")
            st.markdown(f"**Email:** {st.session_state.user_email}")
        with col2:
            if is_verified_status:
                st.success("✅ **Status:** Verified")
            else:
                st.warning("⏳ **Status:** Pending Verification")
        
        from datetime import datetime
        reg_date = datetime.fromtimestamp(registered_at)
        st.markdown(f"**Registered On:** {reg_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not is_verified_status:
            st.info("""💡 **What happens next?**
            
1. An admin will review your registration
2. Once verified, you'll be able to generate certificates
3. Check back here to see your updated status""")
    except Exception as e:
        st.error(f"❌ Error loading status: {str(e)}")

# --- Certificate Generation ---
elif selected == "List Of Certificate":
    files = get_pinata_files(st.session_state.user_email)

    if not files:
        st.info("No files found.")
    else:
        count = 1
        for f in files:
            name = f['metadata'].get('name', 'Unnamed')
            ipfs_hash = f['ipfs_pin_hash']
            link = f"https://gateway.pinata.cloud/ipfs/{ipfs_hash}"
            certificate_id = get_certificate_id_ipfs_hash(ipfs_hash) or "Certificate is not in blockchain"

            col1, col2, col3, col4 = st.columns([2, 3, 4, 2])
            col1.markdown(f"**{count}**")
            col2.markdown(f"[🔗 {name}]({link})", unsafe_allow_html=True)
            col3.markdown(f"`{certificate_id}`")
            if col4.button("Revoke", key=ipfs_hash):
                if certificate_id != "Certificate is not in blockchain":
                    try:
                        # Revoke on blockchain first
                        contract.functions.revokeCertificate(certificate_id).transact({'from': w3.eth.accounts[0]})
                        
                        # Then delete from IPFS
                        if delete_pinata_file(ipfs_hash):
                            st.success("✅ Certificate revoked successfully from blockchain and IPFS!")
                            files.clear()
                            st.rerun()
                        else:
                            st.warning("⚠️ Certificate revoked on blockchain but failed to delete from IPFS.")
                            files.clear()
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to revoke certificate on blockchain: {str(e)}")
                else:
                    # Only delete from IPFS if not on blockchain
                    if delete_pinata_file(ipfs_hash):
                        st.success("✅ File deleted from IPFS!")
                        files.clear()
                        st.rerun()
                    else:
                        st.error("Failed to delete file from Pinata.")
            count += 1

# --- Certificate Generation ---
elif selected == "Generate Certificate":
    next_uid = get_next_uid()

    with st.form("Generate-Certificate"):
        st.markdown("#### Fill the details to generate certificate")
        uid = st.text_input(label="UID", value=next_uid, disabled=True)
        candidate_name = st.text_input(label="Candidate Name")
        course_name = st.text_input(label="Course Name")
        org_name = st.text_input(label="Issuing Organization")

        submit = st.form_submit_button("Generate")

        if submit:
            if not all([uid, candidate_name, course_name, org_name]):
                st.warning("Please fill all fields.")
            else:
                with st.spinner("Generating certificate..."):
                    pdf_file_path = f"{uid}_{candidate_name.strip().replace(" ", "_").lower()}.pdf"
                    institute_logo_path = "../assets/logo.jpg"

                    generate_certificate(pdf_file_path, uid, candidate_name, course_name, org_name, institute_logo_path)

                    # Encrypt the PDF before uploading
                    encryption_key = generate_key()
                    encrypted_bytes = encrypt_file(pdf_file_path, encryption_key)
                    encrypted_filename = f"{os.path.splitext(pdf_file_path)[0]}.enc"

                    ipfs_hash = upload_bytes_to_pinata(encrypted_bytes, encrypted_filename, st.session_state.user_email)
                    os.remove(pdf_file_path)

                    if ipfs_hash:
                        # Generate random salt for hash uniqueness
                        salt = os.urandom(16).hex()
                        data = f"{salt}{uid}{candidate_name}{course_name}{org_name}".encode("utf-8")
                        certificate_id = hashlib.sha256(data).hexdigest()

                        # Create certificate data for digital signature
                        certificate_data = {
                            "uid": uid,
                            "candidate_name": candidate_name,
                            "course_name": course_name,
                            "org_name": org_name,
                            "ipfs_hash": ipfs_hash,
                            "certificate_id": certificate_id,
                            "salt": salt
                        }

                        # Generate digital signature
                        digital_signature = crypto_auth.sign_certificate_data(
                            st.session_state.user_email, 
                            certificate_data
                        )

                        # Store on Blockchain
                        try:
                            contract.functions.generateCertificate(
                                certificate_id, 
                                uid, 
                                candidate_name, 
                                course_name, 
                                org_name, 
                                ipfs_hash,
                                st.session_state.user_email,
                                digital_signature,
                                salt
                            ).transact({'from': w3.eth.accounts[0]})
                            uid_created(next_uid)

                            # Save encryption key with access control
                            save_encryption_key(certificate_id, encryption_key, st.session_state.user_email)

                            st.success(f"✅ Certificate created with digital signature and encryption!")
                            st.success(f"Certificate ID: `{certificate_id}`")
                            st.info("🔐 This certificate is encrypted and digitally signed.")

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
                            else:
                                st.warning("Could not fetch the certificate PDF from IPFS.")
                        except Exception as e:
                            st.error(f"⚠️ Blockchain transaction failed: {str(e)}")

# --- Certificate Viewing ---
elif selected == "View Certificates":
    with st.form("View-Certificate"):
        st.markdown("#### Enter your Certificate ID to view it")
        certificate_id = st.text_input("Certificate ID")
        submit = st.form_submit_button("View")

        if submit:
            if not certificate_id.strip():
                st.warning("Please enter a Certificate ID.")
            else:
                with st.spinner("Fetching certificate..."):
                    try:
                        view_certificate(certificate_id, st.session_state.user_email, user_role="institute")
                    except Exception as e:
                        print(e)
                        st.error("❌ Invalid Certificate ID or blockchain error.")
