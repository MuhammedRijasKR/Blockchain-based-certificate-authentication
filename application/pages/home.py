import streamlit as st

from utils.streamlit_utils import get_image_base64
from utils.auth import AuthManager
from utils.streamlit_utils import hide_sidebar

hide_sidebar()
auth_manager = AuthManager()
auth_manager.redirect_authenticated_user()

# Centered title
st.markdown("<h1 style='text-align: center;'>🎓 Certificate Validation System</h1>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center;'>Please select your role to continue</h4>", unsafe_allow_html=True)
st.markdown("##")

# Layout columns for role selection
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    col_left, col_right = st.columns(2)

    with col_left:
        institute_logo = get_image_base64("../assets/institute_logo.png")
        institute_logo_html = f"""
            <img src="data:image/png;base64,{institute_logo}" width="300" height="160">
        """
        st.markdown(institute_logo_html, unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Institute</p>", unsafe_allow_html=True)

        clicked_institute = st.button("Login as Institute", use_container_width=True)

    with col_right:
        company_logo = get_image_base64("../assets/company_logo.jpg")
        company_logo_html = f"""
                        <img src="data:image/png;base64,{company_logo}" width="300" height="160">
                    """
        st.markdown(company_logo_html, unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Verifier</p>", unsafe_allow_html=True)

        clicked_verifier = st.button("Login as Verifier", use_container_width=True)

# Action handlers
if clicked_institute:
    st.session_state["profile"] = "Institute"
    st.switch_page("pages/institute/institute_login.py")
elif clicked_verifier:
    st.session_state['profile'] = "Verifier"
    st.switch_page('pages/verifier/verifier_login.py')
