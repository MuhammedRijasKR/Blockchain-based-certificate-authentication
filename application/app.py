import streamlit as st

from utils.auth import AuthManager

auth = AuthManager()

st.markdown("""
<style>
    .st-emotion-cache-1jicfl2 {display: none !important;}
    section[data-testid="stSidebar"] {display: none !important;}
    .stSidebar {display: none !important;}
    button[kind="header"] {display: none !important;}
</style>
""", unsafe_allow_html=True)

if auth.is_authenticated():
    logout_btn = st.button("Logout")

    if logout_btn:
        auth.logout()
        st.switch_page("pages/home.py")

pages = [
    st.Page("pages/home.py", title="Home"),

    st.Page("pages/institute/institute.py", title="Institute"),
    st.Page("pages/institute/institute_login.py", title="Institute | Login"),
    st.Page("pages/institute/institute_register.py", title="Institute | Register"),

    st.Page("pages/verifier/verifier.py", title="Verifier"),
    st.Page("pages/verifier/verifier_login.py", title="Verifier | Login"),
    st.Page("pages/verifier/verifier_register.py", title="Verifier | Register"),
]

pg = st.navigation(pages)
pg.run()
