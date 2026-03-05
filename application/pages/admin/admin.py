import streamlit as st
from connection import contract, w3
from utils.auth import AuthManager
from utils.streamlit_utils import hide_sidebar
from datetime import datetime

hide_sidebar()
auth = AuthManager()

# List of allowed admin emails - add your admin emails here
ADMIN_EMAILS = [
    "admin@blockcert.com",
    "admin@example.com",
    "admin@bc.com",
    # Add more admin emails as needed
]

auth.require_auth(allowed_roles=("admin",))

st.markdown("<h1 style='text-align: center;'>🛡️ Admin Dashboard</h1>", unsafe_allow_html=True)
st.markdown("---")

# Tabs for different admin functions
tab1, tab2, tab3 = st.tabs(["⏳ Pending Institutes", "✅ Verified Institutes", "📊 Statistics"])

# --- Pending Institutes Tab ---
with tab1:
    st.markdown("### Institutes Awaiting Verification")
    
    # Import institute details utility
    from utils.institute_details import get_institute_details
    
    try:
        # Get all institute emails from blockchain
        institute_emails = contract.functions.getAllInstituteEmails().call()
        
        pending_institutes = []
        for email in institute_emails:
            try:
                institute_info = contract.functions.getInstitute(email).call()
                name, public_key, is_verified, registered_at = institute_info
                if not is_verified:
                    # Get additional details from JSON
                    details = get_institute_details(email)
                    pending_institutes.append({
                        "email": email,
                        "name": name,
                        "public_key": public_key,
                        "registered_at": registered_at,
                        "details": details
                    })
            except Exception:
                continue
        
        if not pending_institutes:
            st.info("🎉 No pending institutes. All institutes have been verified!")
        else:
            st.warning(f"⚠️ {len(pending_institutes)} institute(s) awaiting verification")
            
            for idx, institute in enumerate(pending_institutes):
                details = institute.get('details', {})
                with st.expander(f"📋 {institute['name']} ({institute['email']})", expanded=True):
                    
                    # Action buttons at top
                    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
                    with col_btn1:
                        if st.button("✅ Verify", key=f"verify_{idx}", type="primary", use_container_width=True):
                            try:
                                contract.functions.verifyInstitute(
                                    institute['email']
                                ).transact({'from': w3.eth.accounts[0]})
                                st.success(f"✅ {institute['name']} has been verified!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Verification failed: {str(e)}")
                    with col_btn2:
                        if st.button("❌ Reject", key=f"reject_{idx}", type="secondary", use_container_width=True):
                            st.warning("⚠️ Rejection feature coming soon.")
                    
                    st.markdown("---")
                    
                    # Basic Info
                    st.markdown("##### 🏛️ Basic Information")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"**Name:** {institute['name']}")
                        st.markdown(f"**Email:** {institute['email']}")
                    with col2:
                        st.markdown(f"**Type:** {details.get('institute_type', 'N/A')}")
                        st.markdown(f"**Established:** {details.get('established_year', 'N/A')}")
                    with col3:
                        reg_date = datetime.fromtimestamp(institute['registered_at'])
                        st.markdown(f"**Registered:** {reg_date.strftime('%Y-%m-%d %H:%M')}")
                        st.markdown(f"**Accreditation:** {details.get('accreditation', 'N/A')}")
                    
                    # Contact Info
                    st.markdown("##### 📞 Contact Information")
                    col4, col5 = st.columns(2)
                    with col4:
                        st.markdown(f"**Phone:** {details.get('phone_number', 'N/A')}")
                        st.markdown(f"**Website:** {details.get('website', 'N/A')}")
                    with col5:
                        st.markdown(f"**Address:** {details.get('address', 'N/A')}")
                    
                    # Verification Documents
                    st.markdown("##### 📄 Verification Documents")
                    st.markdown(f"**Registration/License Number:** `{details.get('registration_number', 'N/A')}`")
                    
                    # Contact Person
                    st.markdown("##### 👤 Contact Person")
                    col6, col7, col8 = st.columns(3)
                    with col6:
                        st.markdown(f"**Name:** {details.get('contact_person_name', 'N/A')}")
                    with col7:
                        st.markdown(f"**Designation:** {details.get('contact_person_designation', 'N/A')}")
                    with col8:
                        st.markdown(f"**Phone:** {details.get('contact_person_phone', 'N/A')}")
                    
                    # Public Key
                    with st.expander("🔑 View Public Key"):
                        st.code(institute['public_key'], language="text")
    
    except Exception as e:
        st.error(f"❌ Error loading institutes: {str(e)}")

# --- Verified Institutes Tab ---
with tab2:
    st.markdown("### Verified Institutes")
    
    try:
        institute_emails = contract.functions.getAllInstituteEmails().call()
        
        verified_institutes = []
        for email in institute_emails:
            try:
                institute_info = contract.functions.getInstitute(email).call()
                name, public_key, is_verified, registered_at = institute_info
                if is_verified:
                    verified_institutes.append({
                        "email": email,
                        "name": name,
                        "public_key": public_key,
                        "registered_at": registered_at
                    })
            except Exception:
                continue
        
        if not verified_institutes:
            st.info("No verified institutes yet.")
        else:
            st.success(f"✅ {len(verified_institutes)} verified institute(s)")
            
            for institute in verified_institutes:
                with st.expander(f"✅ {institute['name']} ({institute['email']})"):
                    st.markdown(f"**Name:** {institute['name']}")
                    st.markdown(f"**Email:** {institute['email']}")
                    
                    reg_date = datetime.fromtimestamp(institute['registered_at'])
                    st.markdown(f"**Registered:** {reg_date.strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    with st.expander("View Public Key"):
                        st.code(institute['public_key'], language="text")
    
    except Exception as e:
        st.error(f"❌ Error loading institutes: {str(e)}")

# --- Statistics Tab ---
with tab3:
    st.markdown("### System Statistics")
    
    try:
        institute_emails = contract.functions.getAllInstituteEmails().call()
        certificate_ids = contract.functions.getAllCertificateIds().call()
        
        # Count verified vs pending
        verified_count = 0
        pending_count = 0
        for email in institute_emails:
            try:
                institute_info = contract.functions.getInstitute(email).call()
                if institute_info[2]:  # is_verified
                    verified_count += 1
                else:
                    pending_count += 1
            except Exception:
                continue
        
        # Display stats in columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📜 Total Certificates", len(certificate_ids))
        
        with col2:
            st.metric("🏛️ Total Institutes", len(institute_emails))
        
        with col3:
            st.metric("✅ Verified Institutes", verified_count)
        
        with col4:
            st.metric("⏳ Pending Verification", pending_count)
        
        st.markdown("---")
        
        # Contract info
        st.markdown("### 🔗 Smart Contract Info")
        st.code(f"Contract Address: {contract.address}", language="text")
        
    except Exception as e:
        st.error(f"❌ Error loading statistics: {str(e)}")
