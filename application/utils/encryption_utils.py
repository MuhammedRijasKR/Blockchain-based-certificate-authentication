"""
Encryption utilities for certificate PDF files.
Uses AES-256-CBC encryption with per-certificate keys.
Keys are stored locally in a JSON key store with attribute-based access control.
"""
import json
import os

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


KEY_STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "encryption_keys.json")


def _load_key_store():
    """Load the encryption key store from disk."""
    if os.path.exists(KEY_STORE_PATH):
        with open(KEY_STORE_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_key_store(store):
    """Save the encryption key store to disk."""
    with open(KEY_STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


def generate_key():
    """Generate a random 32-byte AES-256 key."""
    return os.urandom(32)


def encrypt_file(file_path, key):
    """
    Encrypt a file using AES-256-CBC.
    Returns encrypted bytes with IV prepended.
    """
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)

    with open(file_path, "rb") as f:
        plaintext = f.read()

    encrypted = cipher.encrypt(pad(plaintext, AES.block_size))
    return iv + encrypted  # Prepend IV for decryption


def decrypt_file(encrypted_bytes, key):
    """
    Decrypt AES-256-CBC encrypted bytes.
    Expects IV prepended to ciphertext.
    Returns decrypted bytes.
    """
    iv = encrypted_bytes[:16]
    ciphertext = encrypted_bytes[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ciphertext), AES.block_size)


def save_encryption_key(certificate_id, key, institute_email):
    """
    Save an encryption key for a certificate.
    Stores institute_email for access control.
    """
    store = _load_key_store()
    store[certificate_id] = {
        "key": key.hex(),
        "institute_email": institute_email
    }
    _save_key_store(store)


def get_encryption_key(certificate_id, user_email, user_role):
    """
    Retrieve an encryption key with attribute-based access control.

    Access rules:
    - admin: can access ALL keys
    - institute: can access only keys for certificates THEY issued
    - verifier: NEVER allowed

    Returns the key bytes or None if access denied.
    """
    store = _load_key_store()
    entry = store.get(certificate_id)

    if entry is None:
        return None

    # Access control checks
    if user_role == "admin":
        return bytes.fromhex(entry["key"])
    elif user_role == "institute":
        if entry["institute_email"] == user_email:
            return bytes.fromhex(entry["key"])
        return None  # Institute can only access their own
    else:
        # Verifiers and any other role: access denied
        return None
