import base64
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding


def generate_key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return {"private_key": private_key, "public_key": public_key}


def save_private_key_to_pem(private_key, email: str):
    filename = f"keys/{email}/private_key.pem"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    with open(filename, 'wb') as f:
        f.write(pem)


def save_public_key_to_pem(public_key, email: str):
    filename = f"keys/{email}/public_key.pem"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(filename, 'wb') as f:
        f.write(pem)


def load_private_key_from_pem(email: str):
    filename = f"keys/{email}/private_key.pem"
    with open(filename, 'rb') as f:
        pem_data = f.read()
    return serialization.load_pem_private_key(pem_data, password=None)


def load_public_key_from_pem(email: str, serialize: bool = True):
    filename = f"keys/{email}/public_key.pem"
    with open(filename, 'rb') as f:
        pem_data = f.read()

    if serialize:
        return serialization.load_pem_public_key(pem_data)
    return pem_data


def sign_data(data: bytes, private_key) -> str:
    signature = private_key.sign(
        data,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode()


def verify_signature(data: bytes, signature_b64: str, public_key) -> bool:
    try:
        public_key.verify(
            base64.b64decode(signature_b64),
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except InvalidSignature:
        return False
