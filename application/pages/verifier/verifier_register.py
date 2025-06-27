import re

import streamlit as st
from db.firebase_app import register
from utils.auth import AuthManager
from utils.streamlit_utils import hide_sidebar

hide_sidebar()
auth = AuthManager()

# --- Title ---
st.markdown(f"<h2 style='text-align: center;'>📝 Verifier Registration</h2>", unsafe_allow_html=True)
st.markdown("##")

# --- Registration Form ---
with st.form("register", clear_on_submit=False):
    st.markdown("#### Create a new account")
    email = st.text_input("Email", placeholder="you@example.com")
    password = st.text_input("Password", type="password", placeholder="Minimum 6 characters")
    submit = st.form_submit_button("Register")

# --- Already Registered Link ---
st.markdown("---")
if st.button("Already registered? Click here to login!"):
    st.switch_page("pages/verifier/verifier_login.py")

# --- Form Submission Logic ---
if submit:
    email = email.strip()
    if not email or not password:
        st.warning("Please fill in both fields.")
    elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        st.warning("Enter a valid email address.")
    elif len(password) < 6:
        st.warning("Password must be at least 6 characters.")
    else:
        if auth.register_user(email, password, "verifier"):
            st.success("✅ Registration successful!")
            st.switch_page("pages/verifier/verifier_login.py")
        else:
            st.error("❌ Registration failed. Email may already be in use.")
