import json
import os
import time

import streamlit as st
from db.firebase_app import register, login, get_user_role
from utils.signature_utils import generate_key_pair, save_public_key_to_pem, save_private_key_to_pem

class AuthManager:
    login_required_redirect_page = {
        "verifier": "pages/verifier/login.py",
        "institute": "pages/institute/login.py",
    }
    access_denied_redirect_page = {
        "home": "pages/home.py",
        "verifier": "pages/verifier/verifier.py",
        "institute": "pages/institute/institute.py",
    }

    AUTH_FILE = ".streamlit_auth.json"

    @staticmethod
    def _save_auth_state(email, role):
        """Save auth state to file"""
        try:
            auth_data = {
                "email": email,
                "role": role,
                "timestamp": time.time(),
                "expires": time.time() + (24 * 3600)  # 24 hours
            }
            with open(AuthManager.AUTH_FILE, 'w') as f:
                json.dump(auth_data, f)
        except:
            pass  # Fail silently if can't write file

    @staticmethod
    def _load_auth_state():
        """Load auth state from file"""
        try:
            if os.path.exists(AuthManager.AUTH_FILE):
                with open(AuthManager.AUTH_FILE, 'r') as f:
                    auth_data = json.load(f)

                # Check if not expired
                if time.time() < auth_data.get('expires', 0):
                    return auth_data
                else:
                    # Remove expired file
                    os.remove(AuthManager.AUTH_FILE)
        except:
            pass
        return None

    @staticmethod
    def _clear_auth_state():
        """Clear saved auth state"""
        try:
            if os.path.exists(AuthManager.AUTH_FILE):
                os.remove(AuthManager.AUTH_FILE)
        except:
            pass

    @staticmethod
    def register_user(email, password, role):
        """Register new user"""
        key_pair = generate_key_pair()
        save_private_key_to_pem(key_pair.get('private_key'), email)
        save_public_key_to_pem(key_pair.get('public_key'), email)
        return register(email, password, role)

    @staticmethod
    def login(email, password):
        """Login user with file persistence"""
        user_id = login(email, password)
        role = get_user_role(user_id)
        if user_id:
            st.session_state.authenticated = True
            st.session_state.user_role = role
            st.session_state.user_email = email

            AuthManager._save_auth_state(email, role)

            return role
        return False

    @staticmethod
    def logout():
        """Logout user"""
        for key in ['authenticated', "user_role", "user_email"]:
            if key in st.session_state:
                del st.session_state[key]

        # Clear saved auth state
        AuthManager._clear_auth_state()

    @staticmethod
    def is_authenticated():
        """Check if user is authenticated, restore from file if needed"""
        if not st.session_state.get('authenticated', False):
            # Try to restore from saved state
            auth_data = AuthManager._load_auth_state()
            if auth_data:
                st.session_state.authenticated = True
                st.session_state.user_role = auth_data['role']
                st.session_state.user_email = auth_data['email']
                return True

        return st.session_state.get('authenticated', False)

    def redirect_authenticated_user(self):
        if self.is_authenticated():
            role = st.session_state.user_role or "home"
            st.switch_page(self.access_denied_redirect_page[role])

    def require_auth(self, allowed_roles=None):
        """Decorator/function to require authentication"""
        user_role = st.session_state.get('user_role')
        if not self.is_authenticated():
            st.error("Please login to access this page")
            if self.login_required_redirect_page:
                st.switch_page(self.login_required_redirect_page.get(user_role))
            st.stop()

        if allowed_roles:
            if user_role not in allowed_roles:
                st.error("You don't have permission to access this page")
                if user_role in self.access_denied_redirect_page:
                    st.switch_page(self.access_denied_redirect_page[user_role])
                st.stop()
