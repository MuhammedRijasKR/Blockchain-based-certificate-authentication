from time import sleep

import streamlit as st
from dotenv import load_dotenv
from utils.auth import AuthManager
from utils.streamlit_utils import hide_sidebar

hide_sidebar()
auth = AuthManager()

load_dotenv()

# Redirect if already authenticated as admin
if auth.is_authenticated() and st.session_state.get('user_role') == 'admin':
    st.switch_page("pages/admin/admin.py")

# --- Title ---
st.markdown("<h2 style='text-align: center;'>🛡️ Admin Login</h2>", unsafe_allow_html=True)
st.markdown("##")

# --- Login Form ---
with st.form("admin_login", clear_on_submit=False):
    st.markdown("#### Please enter your admin credentials")
    email = st.text_input("Email", placeholder="admin@blockcert.com")
    password = st.text_input("Password", type="password", placeholder="••••••••")

    submit = st.form_submit_button("Login")

# --- Registration Prompt ---
st.markdown("---")
if st.button("New admin? Click here to register"):
    st.switch_page("pages/admin/admin_register.py")

# --- Back to Home ---
if st.button("← Back to Home"):
    st.switch_page("pages/home.py")

# --- Form Logic ---
if submit:
    if not email or not password:
        st.warning("Please enter both email and password.")
    else:
        email = email.strip()
        role = auth.login(email=email, password=password)
        
        if not role or role != "admin":
            st.error("❌ Invalid credentials or not an admin account.")
            sleep(2)
            auth.logout()
            st.rerun()

        st.success("✅ Login successful!")
        st.switch_page("pages/admin/admin.py")
