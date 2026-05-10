import base64
import json
import os
import tempfile
import time
from io import BytesIO

import requests
import streamlit as st
from PIL import Image
from connection import contract
from utils.pinata_utils import get_metadata_from_pinata
from utils.encryption_utils import get_encryption_key, decrypt_file


def displayPDF(file):
    # Opening file from file path
    with open(file, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')

    # Embedding PDF in HTML
    pdf_display = F'<iframe src="data:application/pdf;base64,{base64_pdf}" width="700" height="1000" type="application/pdf"></iframe>'

    # Displaying File
    st.markdown(pdf_display, unsafe_allow_html=True)


def view_certificate(certificate_id, user_email=None, user_role=None):
    ipfs_hash = None
    is_batch_cert = False

    # Try individual certificate first
    try:
        result = contract.functions.getCertificate(certificate_id).call()
        ipfs_hash = result[4]
    except Exception:
        pass

    # Fall back to batch certificate lookup
    if not ipfs_hash:
        from utils.merkle_utils import find_certificate_batch
        batch_id, batch_cert_data = find_certificate_batch(certificate_id)
        if batch_id is not None and batch_cert_data:
            ipfs_hash = batch_cert_data.get("ipfs_hash", "")
            is_batch_cert = True

    if not ipfs_hash:
        st.error("❌ Certificate not found on blockchain or in any batch.")
        return

    # Access control for institute users
    if not is_batch_cert:
        metadata = get_metadata_from_pinata(ipfs_hash)
        if user_email is not None and user_role == "institute" and metadata and metadata.get("keyvalues", {}).get("user_email") != str(user_email):
            raise Exception("User email does not match")

    # Resolve viewer identity
    if user_role is None:
        user_role = st.session_state.get("user_role", "verifier")
    if user_email is None:
        user_email = st.session_state.get("user_email", "")

    # Note: face-ID gating is enforced in the verifier flow (see verifier.py).
    # The institute/admin viewing their own certificate is gated by the
    # encryption-key ABAC below — no live face capture is required here.

    encryption_key = get_encryption_key(certificate_id, user_email, user_role)

    pinata_gateway_base_url = 'https://gateway.pinata.cloud/ipfs'
    content_url = f"{pinata_gateway_base_url}/{ipfs_hash}"
    response = requests.get(content_url)

    if encryption_key:
        # Decrypt the PDF
        try:
            decrypted_bytes = decrypt_file(response.content, encryption_key)
            # Header banner with the certificate ID for copy/share.
            st.markdown("##### 🆔 Certificate ID")
            st.code(certificate_id, language=None)
            if is_batch_cert:
                st.caption("This certificate was issued as part of a Merkle batch.")

            tmp_fd, tmp_path = tempfile.mkstemp(prefix="cert_view_", suffix=".pdf")
            try:
                with os.fdopen(tmp_fd, "wb") as pdf_file:
                    pdf_file.write(decrypted_bytes)
                displayPDF(tmp_path)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            st.download_button(
                label="📥 Download Certificate PDF",
                data=decrypted_bytes,
                file_name=f"certificate_{certificate_id[:12]}.pdf",
                mime="application/pdf",
                key=f"view_cert_dl_{certificate_id}",
            )
        except Exception as e:
            st.error(f"❌ Failed to decrypt certificate: {str(e)}")
    else:
        st.error("🔒 Access denied: You do not have permission to view this certificate.")


def hide_icons():
    hide_st_style = """
				<style>
				#MainMenu {visibility: hidden;}
				footer {visibility: hidden;}
				</style>"""
    st.markdown(hide_st_style, unsafe_allow_html=True)


def hide_sidebar():
    st.markdown("""
    <style>
        .st-emotion-cache-1jicfl2 {display: none !important;}
        section[data-testid="stSidebar"] {display: none !important;}
        .stSidebar {display: none !important;}
        button[kind="header"] {display: none !important;}
    </style>
    """, unsafe_allow_html=True)


def remove_whitespaces():
    st.markdown("""
        <style>
               .css-18e3th9 {
                    padding-top: 0rem;
                    padding-bottom: 10rem;
                    padding-left: 5rem;
                    padding-right: 5rem;
                }
               .css-1d391kg {
                    padding-top: 3.5rem;
                    padding-right: 1rem;
                    padding-bottom: 3.5rem;
                    padding-left: 1rem;
                }
        </style>""", unsafe_allow_html=True)


def get_image_base64(img_path):
    img = Image.open(img_path)
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


def _acquire_uid_lock(file_path, timeout=10.0):
    """Best-effort cross-process advisory lock for the UID counter.

    Uses a sibling ``<file>.lock`` file with exclusive create. Retries until
    ``timeout`` elapses, after which it forcibly takes the lock to avoid
    deadlocking on a stale lock file.
    """
    lock_path = file_path + ".lock"
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return lock_path
        except FileExistsError:
            if time.time() >= deadline:
                # Forcibly reclaim the lock
                try:
                    os.remove(lock_path)
                except OSError:
                    pass
            else:
                time.sleep(0.05)


def _release_uid_lock(lock_path):
    try:
        os.remove(lock_path)
    except OSError:
        pass


def get_next_uid(file_path="last_uid.json", start_uid=1000):
    """Reads last UID from JSON file, increments it, saves new UID with timestamp."""
    lock = _acquire_uid_lock(file_path)
    try:
        if not os.path.exists(file_path):
            data = {
                "last_uid": start_uid,
                "created": False,
            }
            with open(file_path, "w") as f:
                json.dump(data, f, indent=4)
            return str(start_uid)

        with open(file_path, "r") as f:
            data = json.load(f)

        new_uid = data["last_uid"] + 1 if data["created"] else data["last_uid"]
        data = {
            "last_uid": new_uid,
            "created": False,
        }

        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)

        return str(new_uid)
    finally:
        _release_uid_lock(lock)


def uid_created(uid, file_path="last_uid.json"):
    """Marks the given UID as created by setting the flag to True in the JSON file."""
    lock = _acquire_uid_lock(file_path)
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError("UID file does not exist.")

        with open(file_path, "r") as f:
            data = json.load(f)

        if str(data["last_uid"]) != str(uid):
            raise ValueError(f"UID {uid} does not match the current UID ({data['last_uid']}).")

        data["created"] = True

        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    finally:
        _release_uid_lock(lock)
