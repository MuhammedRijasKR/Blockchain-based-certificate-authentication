import hashlib
import os
import json

import streamlit as st
from connection import contract, w3
from dotenv import load_dotenv
from utils.auth import AuthManager
from utils.cert_utils import generate_certificate, get_certificate_id_ipfs_hash
from utils.pinata_utils import upload_to_pinata, delete_pinata_file, get_pinata_files
from utils.streamlit_utils import hide_sidebar
from utils.streamlit_utils import view_certificate, get_next_uid, uid_created
from utils.crypto_utils import DigitalCertificateAuth

hide_sidebar()
auth = AuthManager()
crypto_auth = DigitalCertificateAuth()

auth.require_auth(allowed_roles=("institute",))

load_dotenv()

# --- UI: Role Selection ---
st.markdown("<h2 style='text-align: center;'>🎓 Certificate Validation System</h2>", unsafe_allow_html=True)
st.write("")

options = ("Institute Registration", "List Of Certificate", "Generate Certificate", "View Certificates", "Export Credentials")
selected = st.selectbox("Select an option", options, label_visibility="collapsed")

# --- Institute Registration ---
if selected == "Institute Registration":
    st.markdown("### 🏛️ Institute Registration")
    st.write("Register your institute to issue digitally signed certificates.")
    
    with st.form("Institute-Registration"):
        institute_name = st.text_input("Institute Name")
        institute_email = st.text_input("Institute Email", value=st.session_state.user_email, disabled=True)
        
        # Generate keys if not exists
        private_key_path, public_key_path = crypto_auth.get_institute_keys(institute_email)
        if not os.path.exists(private_key_path):
            crypto_auth.generate_institute_keys(institute_email)
            st.success("✅ Cryptographic keys generated for your institute.")
        
        # Display public key
        if os.path.exists(public_key_path):
            with open(public_key_path, 'r') as f:
                public_key = f.read()
            st.text_area("Your Public Key (for verification)", public_key, height=150)
        
        submit = st.form_submit_button("Register Institute")
        
        if submit:
            if not institute_name:
                st.warning("Please enter institute name.")
            else:
                try:
                    # Register institute on blockchain (auto-verified)
                    contract.functions.registerInstitute(
                        institute_email,
                        institute_name,
                        public_key
                    ).transact({'from': w3.eth.accounts[0]})
                    # Immediately verify the institute
                    contract.functions.verifyInstitute(institute_email).transact({'from': w3.eth.accounts[0]})
                    st.success("✅ Institute registered and automatically verified! You can now issue certificates.")
                except Exception as e:
                    st.error(f"❌ Registration failed: {str(e)}")

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

                    ipfs_hash = upload_to_pinata(pdf_file_path, st.session_state.user_email)
                    os.remove(pdf_file_path)

                    if ipfs_hash:
                        data = f"{uid}{candidate_name}{course_name}{org_name}".encode("utf-8")
                        certificate_id = hashlib.sha256(data).hexdigest()

                        # Create certificate data for digital signature
                        certificate_data = {
                            "uid": uid,
                            "candidate_name": candidate_name,
                            "course_name": course_name,
                            "org_name": org_name,
                            "ipfs_hash": ipfs_hash,
                            "certificate_id": certificate_id
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
                                digital_signature
                            ).transact({'from': w3.eth.accounts[0]})
                            uid_created(next_uid)

                            st.success(f"✅ Certificate created with digital signature!")
                            st.success(f"Certificate ID: `{certificate_id}`")
                            st.info("🔐 This certificate is digitally signed and can be verified by employers.")
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
                        view_certificate(certificate_id, st.session_state.user_email)
                    except Exception as e:
                        print(e)
                        st.error("❌ Invalid Certificate ID or blockchain error.")

# --- Export Credentials ---
elif selected == "Export Credentials":
    st.markdown("### 🔑 Export Institute Credentials")
    st.write("Export your institute's public key for external verification.")
    
    institute_email = st.session_state.user_email
    credentials = crypto_auth.export_institute_credentials(institute_email)
    
    if credentials:
        st.json(credentials)
        
        # Create download button for credentials
        credentials_json = json.dumps(credentials, indent=2)
        st.download_button(
            label="📥 Download Credentials",
            data=credentials_json,
            file_name=f"{institute_email}_credentials.json",
            mime="application/json"
        )
        
        st.info("💡 Share this file with employers or verification services to verify your certificates.")
    else:
        st.error("❌ No credentials found. Please register your institute first.")
