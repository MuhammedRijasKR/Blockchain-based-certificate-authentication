from time import sleep

import streamlit as st
from db.firebase_app import login
from dotenv import load_dotenv
from utils.auth import AuthManager
from utils.streamlit_utils import hide_sidebar

hide_sidebar()
auth = AuthManager()

load_dotenv()

# --- Title ---
st.markdown(f"<h2 style='text-align: center;'>🔐 Institute Login</h2>", unsafe_allow_html=True)
st.markdown("##")

# --- Login Form ---
with st.form("login", clear_on_submit=False):
    st.markdown("#### Please enter your login credentials")
    email = st.text_input("Email", placeholder="your@email.com")
    password = st.text_input("Password", type="password", placeholder="••••••••")

    submit = st.form_submit_button("Login")

# --- Registration Prompt ---
st.markdown("---")
if st.button("New user? Click here to register"):
    st.switch_page("pages/institute/institute_register.py")

# --- Form Logic ---
if submit:
    if not email or not password:
        st.warning("Please enter both email and password.")
    else:
        email = email.strip()
        role = auth.login(email=email, password=password)
        if not role or role != "institute":
            st.error("❌ Invalid email or password.")
            sleep(3)
            auth.logout()
            st.rerun()

        st.success("✅ Login successful!")
        st.switch_page("pages/institute/institute.py")
