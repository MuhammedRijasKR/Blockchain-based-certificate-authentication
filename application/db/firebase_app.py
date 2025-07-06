import os

import firebase_admin
import pyrebase
from dotenv import load_dotenv
from firebase_admin import credentials, auth as admin_auth

load_dotenv()

config = {
    "apiKey": os.getenv("FIREBASE_API_KEY"),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
    "databaseURL": os.getenv("FIREBASE_DATABASE_URL"),
    "projectId": os.getenv("FIREBASE_PROJECT_ID"),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
    "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
    "appId": os.getenv("FIREBASE_APP_ID"),
}

firebase = pyrebase.initialize_app(config)
auth = firebase.auth()

if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)


def set_user_role(email, role):
    try:
        user = admin_auth.get_user_by_email(email)
        admin_auth.set_custom_user_claims(user.uid, {"role": role})
        return True
    except Exception as e:
        print(f"Error setting role: {e}")
        return False


def get_user_role(id_token):
    try:
        decoded = admin_auth.verify_id_token(id_token, clock_skew_seconds=60)
        return decoded.get("role", "none")
    except Exception as e:
        print(f"Error verifying token: {e}")
        return None


def register(email, password, role):
    try:
        auth.create_user_with_email_and_password(email, password)
        set_user_role(email, role)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def login(email, password):
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        if user:
            return user.get("idToken")
        return False
    except Exception as e:
        print(f"Login_Error: {e}")
        return False
