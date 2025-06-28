import hashlib
import os

import streamlit as st
from connection import contract, w3
from dotenv import load_dotenv
from utils.auth import AuthManager
from utils.cert_utils import generate_certificate, get_certificate_id_ipfs_hash
from utils.pinata_utils import upload_to_pinata, delete_pinata_file, get_pinata_files
from utils.streamlit_utils import hide_sidebar
from utils.streamlit_utils import view_certificate, get_next_uid, uid_created

hide_sidebar()
auth = AuthManager()

auth.require_auth(allowed_roles=("institute",))

load_dotenv()

# --- UI: Role Selection ---
st.markdown("<h2 style='text-align: center;'>🎓 Certificate Validation System</h2>", unsafe_allow_html=True)
st.write("")

options = ("List Of Certificate", "Generate Certificate", "View Certificates")
selected = st.selectbox("Select an option", options, label_visibility="collapsed")

# --- Certificate Generation ---
if selected == "List Of Certificate":
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
                if delete_pinata_file(ipfs_hash):
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

                        # Store on Blockchain
                        try:
                            contract.functions.generateCertificate(
                                certificate_id, uid, candidate_name, course_name, org_name, ipfs_hash
                            ).transact({'from': w3.eth.accounts[0]})
                            uid_created(next_uid)

                            st.success(f"✅ Certificate created! Certificate ID:\n`{certificate_id}`")
                        except Exception as e:
                            st.error(f"⚠️ Blockchain transaction failed: {str(e)}")

# --- Certificate Viewing ---
else:
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
