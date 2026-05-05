import streamlit as st
from dotenv import load_dotenv
from utils.auth import AuthManager
from utils.admin_config import ADMIN_EMAILS
from utils.streamlit_utils import hide_sidebar

hide_sidebar()
auth = AuthManager()

load_dotenv()

# Redirect if already authenticated
auth.redirect_authenticated_user()

# --- Title ---
st.markdown("<h2 style='text-align: center;'>🛡️ Admin Registration</h2>", unsafe_allow_html=True)
st.markdown("##")

st.warning("⚠️ Admin registration is restricted. Only pre-approved email addresses can register.")

# --- Registration Form ---
with st.form("admin_register", clear_on_submit=False):
    st.markdown("#### Create your admin account")
    email = st.text_input("Email", placeholder="admin@blockcert.com")
    password = st.text_input("Password", type="password", placeholder="••••••••")
    confirm_password = st.text_input("Confirm Password", type="password", placeholder="••••••••")

    submit = st.form_submit_button("Register")

# --- Login Prompt ---
st.markdown("---")
if st.button("Already have an account? Login here"):
    st.switch_page("pages/admin/admin_login.py")

# --- Back to Home ---
if st.button("← Back to Home"):
    st.switch_page("pages/home.py")

# --- Form Logic ---
if submit:
    if not email or not password or not confirm_password:
        st.warning("Please fill all fields.")
    elif email.strip() not in ADMIN_EMAILS:
        st.error("❌ This email is not authorized for admin registration.")
    elif password != confirm_password:
        st.error("❌ Passwords do not match.")
    elif len(password) < 6:
        st.error("❌ Password must be at least 6 characters.")
    else:
        email = email.strip()
        
        # Register with admin role
        result = auth.register_user(email=email, password=password, role="admin")
        
        if result:
            st.success("✅ Admin account created successfully!")
            st.info("Please login with your new credentials.")
            st.switch_page("pages/admin/admin_login.py")
        else:
            st.error("❌ Registration failed. Email may already be registered.")
