import hashlib
import json
import os
import time
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from cryptography.x509 import load_pem_x509_certificate
import base64
import streamlit as st

class DigitalCertificateAuth:
    def __init__(self):
        self.keys_dir = "keys"
        self.ensure_keys_directory()
    
    def ensure_keys_directory(self):
        """Ensure the keys directory exists"""
        if not os.path.exists(self.keys_dir):
            os.makedirs(self.keys_dir)
    
    def generate_institute_keys(self, institute_email):
        """Generate RSA key pair for an institute"""
        institute_dir = os.path.join(self.keys_dir, institute_email)
        if not os.path.exists(institute_dir):
            os.makedirs(institute_dir)
        
        private_key_path = os.path.join(institute_dir, "private_key.pem")
        public_key_path = os.path.join(institute_dir, "public_key.pem")
        
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        # Generate public key
        public_key = private_key.public_key()
        
        # Save private key
        with open(private_key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Save public key
        with open(public_key_path, "wb") as f:
            f.write(public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))
        
        return private_key_path, public_key_path
    
    def get_institute_keys(self, institute_email):
        """Get institute's key paths"""
        institute_dir = os.path.join(self.keys_dir, institute_email)
        private_key_path = os.path.join(institute_dir, "private_key.pem")
        public_key_path = os.path.join(institute_dir, "public_key.pem")
        
        return private_key_path, public_key_path
    
    def sign_certificate_data(self, institute_email, certificate_data):
        """Sign certificate data with institute's private key"""
        private_key_path, _ = self.get_institute_keys(institute_email)
        
        if not os.path.exists(private_key_path):
            # Generate keys if they don't exist
            self.generate_institute_keys(institute_email)
        
        # Load private key
        with open(private_key_path, "rb") as f:
            private_key = load_pem_private_key(f.read(), password=None)
        
        # Create data to sign
        data_to_sign = json.dumps(certificate_data, sort_keys=True).encode('utf-8')
        
        # Sign the data
        signature = private_key.sign(
            data_to_sign,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return base64.b64encode(signature).decode('utf-8')
    
    def verify_certificate_signature(self, institute_email, certificate_data, signature):
        """Verify certificate signature with institute's public key"""
        _, public_key_path = self.get_institute_keys(institute_email)
        
        if not os.path.exists(public_key_path):
            return False
        
        try:
            # Load public key
            with open(public_key_path, "rb") as f:
                public_key = load_pem_public_key(f.read())
            
            # Create data to verify
            data_to_verify = json.dumps(certificate_data, sort_keys=True).encode('utf-8')
            
            # Decode signature
            signature_bytes = base64.b64decode(signature.encode('utf-8'))
            
            # Verify signature
            public_key.verify(
                signature_bytes,
                data_to_verify,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return True
        except Exception as e:
            print(f"Signature verification failed: {e}")
            return False
    
    def create_digital_certificate(self, institute_email, certificate_data):
        """Create a digital certificate with institute signature"""
        # Add timestamp and institute info
        digital_cert = {
            "certificate_data": certificate_data,
            "institute_email": institute_email,
            "timestamp": int(time.time()),
            "version": "1.0"
        }
        
        # Sign the certificate
        signature = self.sign_certificate_data(institute_email, digital_cert)
        digital_cert["signature"] = signature
        
        return digital_cert
    
    def verify_digital_certificate(self, digital_cert):
        """Verify a digital certificate"""
        try:
            # Extract signature
            signature = digital_cert.pop("signature", None)
            if not signature:
                return False, "No signature found"
            
            # Verify signature
            institute_email = digital_cert.get("institute_email")
            if not institute_email:
                return False, "No institute email found"
            
            is_valid = self.verify_certificate_signature(institute_email, digital_cert, signature)
            
            if is_valid:
                return True, "Certificate signature is valid"
            else:
                return False, "Certificate signature is invalid"
                
        except Exception as e:
            return False, f"Verification error: {str(e)}"
    
    def get_institute_public_key(self, institute_email):
        """Get institute's public key for verification"""
        _, public_key_path = self.get_institute_keys(institute_email)
        
        if os.path.exists(public_key_path):
            with open(public_key_path, "rb") as f:
                return f.read().decode('utf-8')
        return None
    
    def export_institute_credentials(self, institute_email):
        """Export institute credentials for external verification"""
        institute_dir = os.path.join(self.keys_dir, institute_email)
        public_key_path = os.path.join(institute_dir, "public_key.pem")
        
        if os.path.exists(public_key_path):
            with open(public_key_path, "rb") as f:
                public_key = f.read().decode('utf-8')
            
            return {
                "institute_email": institute_email,
                "public_key": public_key,
                "exported_at": int(time.time())
            }
        return None 