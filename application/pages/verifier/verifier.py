import hashlib
import os
import json

import streamlit as st
from connection import contract
from utils.cert_utils import extract_certificate
from utils.auth import AuthManager
from utils.streamlit_utils import hide_sidebar
from utils.crypto_utils import DigitalCertificateAuth

hide_sidebar()
auth = AuthManager()
crypto_auth = DigitalCertificateAuth()

auth.require_auth(allowed_roles=("verifier",))

st.markdown("<h2 style='text-align: center;'>✅ Certificate Verification</h2>", unsafe_allow_html=True)
st.markdown("##")

# --- Options ---
options = ("Verify using PDF", "Verify using Certificate ID", "Institute Verification")
selected = st.selectbox("Select an option", options, label_visibility="collapsed")

# --- Option 1: Upload Certificate PDF ---
if selected == options[0]:
    uploaded_file = st.file_uploader("Upload your Certificate PDF")

    if uploaded_file:
        with open("temp_certificate.pdf", "wb") as file:
            file.write(uploaded_file.getvalue())

        try:
            # Extract certificate contents (not displayed to verifier)
            uid, candidate_name, course_name, org_name = extract_certificate("temp_certificate.pdf")
            os.remove("temp_certificate.pdf")

            st.info("📄 Certificate data extracted. Verifying on blockchain...")

            # Try to find the certificate by matching fields to get the salt
            all_cert_ids = contract.functions.getAllCertificateIds().call()
            certificate_id = None
            salt = None
            
            for cid in all_cert_ids:
                try:
                    cd = contract.functions.getCertificate(cid).call()
                    if cd[0] == uid and cd[1] == candidate_name and cd[2] == course_name and cd[3] == org_name:
                        certificate_id = cid
                        salt = cd[7]  # salt field
                        break
                except Exception:
                    continue
            
            if certificate_id is None:
                st.error("❌ Certificate not found on blockchain.")
                st.stop()

            # Verify the hash with salt
            data_to_hash = f"{salt}{uid}{candidate_name}{course_name}{org_name}".encode('utf-8')
            expected_hash = hashlib.sha256(data_to_hash).hexdigest()
            
            if expected_hash != certificate_id:
                st.error("❌ Certificate hash mismatch - data may have been tampered!")
                st.stop()

            # Check if certificate exists on blockchain
            try:
                cert_data = contract.functions.getCertificate(certificate_id).call()
                
                # Check if revoked
                is_revoked = contract.functions.isRevoked(certificate_id).call()
                
                if is_revoked:
                    st.error("❌ Certificate has been REVOKED and is no longer valid.")
                else:
                    # Verify on blockchain
                    result = contract.functions.isVerified(certificate_id).call()
                    
                    if result:
                        st.success("🎉 Certificate is VALID and registered on blockchain.")
                        
                        # Verify digital signature
                        institute_email = cert_data[5]
                        digital_signature = cert_data[6]
                        
                        certificate_data = {
                            "uid": uid,
                            "candidate_name": candidate_name,
                            "course_name": course_name,
                            "org_name": org_name,
                            "ipfs_hash": cert_data[4],
                            "certificate_id": certificate_id,
                            "salt": salt
                        }
                        
                        signature_valid = crypto_auth.verify_certificate_signature(
                            institute_email, 
                            certificate_data, 
                            digital_signature
                        )
                        
                        if signature_valid:
                            st.success("🔐 Digital signature is VALID - Certificate is authentic!")
                        else:
                            st.error("❌ Digital signature is INVALID - Certificate may be tampered!")
                        
                        # Show institute verification status (no sensitive data)
                        try:
                            institute_info = contract.functions.getInstitute(institute_email).call()
                            st.info(f"🏛️ **Issuing Institute**: {institute_info[0]}")
                            if institute_info[2]:
                                st.success("✅ Institute is verified by the system")
                            else:
                                st.warning("⚠️ Institute is not verified by the system")
                        except:
                            st.warning("⚠️ Could not retrieve institute information")
                    else:
                        st.error("❌ Certificate is INVALID or not registered.")
                        
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
            try:
                # Check if certificate exists and get data
                cert_data = contract.functions.getCertificate(certificate_id).call()
                
                # Check revocation status
                is_revoked = contract.functions.isRevoked(certificate_id).call()
                
                if is_revoked:
                    st.error("❌ Certificate has been REVOKED and is no longer valid.")
                else:
                    # Verify on blockchain (no PDF display for verifier)
                    result = contract.functions.isVerified(certificate_id).call()
                    if result:
                        st.success("🎉 Certificate is VALID and registered on blockchain.")
                        
                        # Verify digital signature
                        institute_email = cert_data[5]
                        digital_signature = cert_data[6]
                        
                        certificate_data = {
                            "uid": cert_data[0],
                            "candidate_name": cert_data[1],
                            "course_name": cert_data[2],
                            "org_name": cert_data[3],
                            "ipfs_hash": cert_data[4],
                            "certificate_id": certificate_id,
                            "salt": cert_data[7]
                        }
                        
                        signature_valid = crypto_auth.verify_certificate_signature(
                            institute_email, 
                            certificate_data, 
                            digital_signature
                        )
                        
                        if signature_valid:
                            st.success("🔐 Digital signature is VALID - Certificate is authentic!")
                        else:
                            st.error("❌ Digital signature is INVALID - Certificate may be tampered!")
                        
                        # Show institute verification status (no sensitive data)
                        try:
                            institute_info = contract.functions.getInstitute(institute_email).call()
                            st.info(f"🏛️ **Issuing Institute**: {institute_info[0]}")
                            if institute_info[2]:
                                st.success("✅ Institute is verified by the system")
                            else:
                                st.warning("⚠️ Institute is not verified by the system")
                        except:
                            st.warning("⚠️ Could not retrieve institute information")
                    else:
                        st.error("❌ Certificate ID is INVALID or not found.")
                        
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
                
                if institute_info[2]:  # is_verified
                    st.success("✅ Institute is VERIFIED and can issue certificates")
                else:
                    st.warning("⚠️ Institute is NOT VERIFIED yet")
                
                # Display public key
                public_key = institute_info[1]
                if public_key:
                    st.text_area("Public Key", public_key, height=150)
                
            except Exception as e:
                st.error("❌ Institute not found in the system.")
