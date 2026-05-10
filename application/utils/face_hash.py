"""Hash an enrolled face profile so the binding can be anchored on-chain.

The hash is taken over the raw embedding bytes (``embeddings.npy`` for the
certificate). Tampering with the stored profile will change the hash and
break verification at the verifier.
"""

import hashlib
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
FACE_STORE_DIR = BASE_DIR / "face_profiles"


def _embeddings_path(certificate_id):
    return FACE_STORE_DIR / certificate_id / "embeddings.npy"


def hash_embeddings_bytes(emb_bytes):
    """Return ``bytes32`` keccak-style sha256 digest of the embedding bytes."""
    return hashlib.sha256(emb_bytes).digest()


def hash_face_profile(certificate_id):
    """Return the sha256 digest of the certificate's stored embeddings.

    Returns ``None`` when no profile is bound.
    """
    path = _embeddings_path(certificate_id)
    if not path.exists():
        return None
    arr = np.load(path)
    return hashlib.sha256(arr.tobytes()).digest()


def hash_embedding_array(arr):
    """Hash an in-memory embedding array (used at issuance, before persisting)."""
    if arr is None:
        return None
    arr = np.ascontiguousarray(arr.astype(np.float32))
    return hashlib.sha256(arr.tobytes()).digest()
