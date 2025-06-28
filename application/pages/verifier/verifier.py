import hashlib
import os

import streamlit as st
from connection import contract
from utils.cert_utils import extract_certificate
from utils.streamlit_utils import view_certificate, displayPDF
from utils.auth import AuthManager
from utils.streamlit_utils import hide_sidebar

hide_sidebar()
auth = AuthManager()

auth.require_auth(allowed_roles=("verifier",))

st.markdown("<h2 style='text-align: center;'>✅ Certificate Verification</h2>", unsafe_allow_html=True)
st.markdown("##")

# --- Options ---
options = ("Verify using PDF", "Verify using Certificate ID")
selected = st.selectbox("Select an option", options, label_visibility="collapsed")

# --- Option 1: Upload Certificate PDF ---
if selected == options[0]:
    uploaded_file = st.file_uploader("Upload your Certificate PDF")

    if uploaded_file:
        with open("temp_certificate.pdf", "wb") as file:
            file.write(uploaded_file.getvalue())

        try:
            # Extract and show certificate contents
            uid, candidate_name, course_name, org_name = extract_certificate("temp_certificate.pdf")
            st.success("✅ Certificate data extracted successfully:")
            st.write(f"- **UID**: {uid}")
            st.write(f"- **Candidate Name**: {candidate_name}")
            st.write(f"- **Course**: {course_name}")
            st.write(f"- **Organization**: {org_name}")

            # Generate hash
            data_to_hash = f"{uid}{candidate_name}{course_name}{org_name}".encode('utf-8')
            certificate_id = hashlib.sha256(data_to_hash).hexdigest()

            # Verify on blockchain
            result = contract.functions.isVerified(certificate_id).call()

            if result:
                st.success("🎉 Certificate is VALID and registered on blockchain.")
            else:
                st.error("❌ Certificate is INVALID or not registered.")

            displayPDF("temp_certificate.pdf")
            os.remove("temp_certificate.pdf")

        except Exception as e:
            st.error("❌ Could not process this certificate. It might be tampered or corrupted.")

# --- Option 2: Enter Certificate ID ---
elif selected == options[1]:
    with st.form("Validate-Certificate"):
        certificate_id = st.text_input("Enter the Certificate ID")
        submit = st.form_submit_button("Validate")

    if submit:
        if not certificate_id.strip():
            st.warning("Please enter a certificate ID.")
        else:
            try:
                # Show certificate
                view_certificate(certificate_id)

                # Smart Contract Call
                result = contract.functions.isVerified(certificate_id).call()
                if result:
                    st.success("🎉 Certificate is VALID and registered on blockchain.")
                else:
                    st.error("❌ Certificate ID is INVALID or not found.")
            except Exception as e:
                print(e)
                st.error("❌ Error validating certificate. Please check the Certificate ID.")
