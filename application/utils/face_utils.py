"""
Face authentication using OpenCV's YuNet face detector + SFace embedding model.

This replaces the previous LBPH-based approach. LBPH on grayscale Haar crops
could not reliably reject unenrolled people or distinguish similar-looking
faces. SFace produces 128-d embeddings that compare via cosine similarity,
where a score >= FACE_MATCH_THRESHOLD (default 0.363, OpenCV recommended)
reliably means "same person".

The two ONNX models are auto-downloaded once on first use into
``application/models/``.

Public API (unchanged from previous module):
    save_face_samples(cert_id, image_sources, owner_name, institute_email, replace=True)
    enroll_face_for_cert(cert_id, image_source, owner_name, institute_email)
    verify_face_match(cert_id, image_source) -> (is_match, score, message)
    clear_face_profile(cert_id)
    get_face_profile(cert_id), face_profile_exists(cert_id), get_face_sample_count(cert_id)
"""

import json
import os
import shutil
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parent.parent
FACE_STORE_DIR = BASE_DIR / "face_profiles"
FACE_INDEX_PATH = BASE_DIR / "face_profiles.json"
MODELS_DIR = BASE_DIR / "models"

# SFace cosine similarity: 1.0 == identical. OpenCV's published LFW cutoff
# is 0.363, but in practice, real webcam captures of GENUINE pairs land at
# 0.55-0.85 while different people stay below 0.30. We pick a conservative
# default well above the LFW number to cleanly reject impostors.
#   FACE_MATCH_THRESHOLD: minimum cosine similarity for a positive match.
#   FACE_MATCH_MARGIN:    how much higher the claimed cert's score must be
#                          vs. the next-best enrolled identity (cross-match
#                          guard).
#   FACE_MIN_PIXELS:      minimum width OR height (pixels) of the detected
#                          face. Tiny faces produce noisy embeddings that sit
#                          around 0.4 for everyone -- reject them.
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.55"))
FACE_MATCH_MARGIN = float(os.getenv("FACE_MATCH_MARGIN", "0.07"))
FACE_MIN_PIXELS = int(os.getenv("FACE_MIN_PIXELS", "80"))

# OpenCV Zoo ONNX models (small, public).
YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
    "face_detection_yunet_2023mar.onnx"
)
SFACE_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/"
    "face_recognition_sface_2021dec.onnx"
)
YUNET_PATH = MODELS_DIR / "face_detection_yunet.onnx"
SFACE_PATH = MODELS_DIR / "face_recognition_sface.onnx"

_DETECTOR = None
_RECOGNIZER = None


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, dest)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _get_detector():
    """YuNet face detector (lazy loaded, model auto-downloaded once)."""
    global _DETECTOR
    if _DETECTOR is None:
        _download(YUNET_URL, YUNET_PATH)
        _DETECTOR = cv2.FaceDetectorYN.create(
            str(YUNET_PATH), "", (0, 0),
            score_threshold=0.7,
            nms_threshold=0.3,
            top_k=50,
        )
    return _DETECTOR


def _get_recognizer():
    """SFace embedding model (lazy loaded, model auto-downloaded once)."""
    global _RECOGNIZER
    if _RECOGNIZER is None:
        _download(SFACE_URL, SFACE_PATH)
        _RECOGNIZER = cv2.FaceRecognizerSF.create(str(SFACE_PATH), "")
    return _RECOGNIZER


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------

def _ensure_store():
    FACE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    if not FACE_INDEX_PATH.exists():
        with open(FACE_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)


def _load_index():
    _ensure_store()
    with open(FACE_INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_index(data):
    FACE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FACE_INDEX_PATH.with_name(FACE_INDEX_PATH.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, FACE_INDEX_PATH)


def _coerce_bytes(image_source):
    if image_source is None:
        return None
    if isinstance(image_source, bytes):
        return image_source
    if hasattr(image_source, "getvalue"):
        return image_source.getvalue()
    if hasattr(image_source, "read"):
        return image_source.read()
    return None


def _decode_image(image_bytes):
    if not image_bytes:
        return None
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------

def _detect_largest_face(image_bgr):
    """Return the largest detected face row (15-element ndarray) or None."""
    detector = _get_detector()
    h, w = image_bgr.shape[:2]
    detector.setInputSize((w, h))
    _, faces = detector.detect(image_bgr)
    if faces is None or len(faces) == 0:
        return None
    # Each row: [x, y, w, h, *5_landmarks(10), score]
    return max(faces, key=lambda r: r[2] * r[3])


def _compute_embedding(image_bytes):
    """
    Detect the largest face, align-crop it via SFace's built-in alignment,
    and return its 128-d embedding (float32 ndarray of shape (1, 128)).

    The embedding is returned RAW (unnormalized). Compare two embeddings via
    ``_get_recognizer().match(a, b, cv2.FaceRecognizerSF_FR_COSINE)``.

    Returns (embedding, error_message). Exactly one is None.
    """
    image = _decode_image(image_bytes)
    if image is None:
        return None, "Could not read the image data."

    face_row = _detect_largest_face(image)
    if face_row is None:
        return None, "No face detected in the image."

    # Quality gate: reject faces that are too small to embed reliably.
    fw, fh = float(face_row[2]), float(face_row[3])
    if min(fw, fh) < FACE_MIN_PIXELS:
        return None, (
            f"Face is too small ({int(fw)}x{int(fh)} px, need ≥ "
            f"{FACE_MIN_PIXELS} px). Move closer to the camera or upload a "
            f"higher-resolution photo."
        )

    recognizer = _get_recognizer()
    aligned = recognizer.alignCrop(image, face_row)
    embedding = recognizer.feature(aligned)
    if embedding is None or float(np.linalg.norm(embedding)) == 0.0:
        return None, "Could not compute a valid face embedding."
    return np.asarray(embedding, dtype=np.float32), None


def _cosine_match(emb_a, emb_b):
    """Canonical SFace cosine similarity between two raw embeddings."""
    recognizer = _get_recognizer()
    a = np.ascontiguousarray(emb_a.reshape(1, -1), dtype=np.float32)
    b = np.ascontiguousarray(emb_b.reshape(1, -1), dtype=np.float32)
    return float(recognizer.match(a, b, cv2.FaceRecognizerSF_FR_COSINE))


def _best_match_score(stored_embeddings, live_emb):
    """Highest cosine similarity between any stored embedding and `live_emb`."""
    best = -1.0
    for row in stored_embeddings:
        s = _cosine_match(row, live_emb)
        if s > best:
            best = s
    return best


def _embeddings_path(cert_id):
    return FACE_STORE_DIR / cert_id / "embeddings.npy"


def _load_embeddings(cert_id):
    """Return an (N, 128) array of stored embeddings, or None."""
    path = _embeddings_path(cert_id)
    if not path.exists():
        return None
    try:
        arr = np.load(path)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        return arr.astype(np.float32)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clear_face_profile(certificate_id):
    """Remove a certificate's face profile from disk and the index."""
    profile_dir = FACE_STORE_DIR / certificate_id
    if profile_dir.exists():
        shutil.rmtree(profile_dir)

    index = _load_index()
    if certificate_id in index:
        del index[certificate_id]
        _save_index(index)


def save_face_samples(certificate_id, image_sources, owner_name="",
                      institute_email="", replace=True):
    """
    Persist face samples for a certificate.

    Each image is run through YuNet → SFace to produce a 128-d embedding.
    Embeddings are stored in ``face_profiles/<cert>/embeddings.npy``.

    Args:
        certificate_id: cert ID to bind the face profile to.
        image_sources:  iterable of bytes / file-like / Streamlit UploadedFile.
        owner_name, institute_email: stored in the JSON index.
        replace: if True, wipe any previous profile first; otherwise append.
    """
    _ensure_store()

    new_embeddings = []
    errors = []
    for i, src in enumerate(image_sources, start=1):
        emb, err = _compute_embedding(_coerce_bytes(src))
        if emb is None:
            errors.append(f"Sample {i}: {err}")
            continue
        new_embeddings.append(emb)

    if not new_embeddings:
        return {
            "success": False,
            "sample_count": 0,
            "errors": errors or ["No valid face sample could be processed."],
        }

    # Decide whether to merge with existing embeddings
    if not replace:
        existing = _load_embeddings(certificate_id)
        if existing is not None:
            stacked = np.vstack([existing] + [e.reshape(1, -1) for e in new_embeddings])
        else:
            stacked = np.vstack([e.reshape(1, -1) for e in new_embeddings])
    else:
        # Wipe any old data for this cert first
        if (FACE_STORE_DIR / certificate_id).exists():
            shutil.rmtree(FACE_STORE_DIR / certificate_id)
        stacked = np.vstack([e.reshape(1, -1) for e in new_embeddings])

    (FACE_STORE_DIR / certificate_id).mkdir(parents=True, exist_ok=True)
    np.save(_embeddings_path(certificate_id), stacked)

    # Update index
    index = _load_index()
    prev = index.get(certificate_id, {}) if not replace else {}
    index[certificate_id] = {
        "certificate_id": certificate_id,
        "owner_name": owner_name or prev.get("owner_name", ""),
        "institute_email": institute_email or prev.get("institute_email", ""),
        "sample_count": int(stacked.shape[0]),
        "enrolled_at": int(time.time()),
        "status": "enrolled",
        "model": "sface_v2_raw",
    }
    _save_index(index)

    return {
        "success": True,
        "sample_count": int(stacked.shape[0]),
        "errors": errors,
    }


def enroll_face_for_cert(certificate_id, image_source, owner_name="",
                         institute_email=""):
    """Convenience: enroll a single image (replaces any existing profile)."""
    return save_face_samples(
        certificate_id,
        [image_source],
        owner_name=owner_name,
        institute_email=institute_email,
        replace=True,
    )


def get_face_profile(certificate_id):
    return _load_index().get(certificate_id)


def face_profile_exists(certificate_id):
    return certificate_id in _load_index()


def get_face_sample_count(certificate_id):
    profile = get_face_profile(certificate_id)
    if not profile:
        return 0
    return int(profile.get("sample_count", 0))


def detect_face(image_source):
    """
    Lightweight pre-flight check used by bulk generation.

    Returns (ok: bool, message: str). ``ok`` is True only when an embedding
    could be computed (face detected and large enough). The message is
    human-readable; on success it is "ok".
    """
    emb, err = _compute_embedding(_coerce_bytes(image_source))
    if emb is None:
        return False, err or "Could not extract a face."
    return True, "ok"


def verify_face_match(certificate_id, image_source,
                      threshold=FACE_MATCH_THRESHOLD,
                      margin=FACE_MATCH_MARGIN):
    """
    Verify a live face image against a certificate's enrolled embedding(s).

    Decision rule (cosine similarity, higher is better):
        1. Live face must produce a usable embedding.
        2. Best similarity to the *claimed* cert >= ``threshold``  → otherwise
           reject ("face does not match"). This catches unenrolled people.
        3. No *other* enrolled cert may exceed the claimed score by more than
           ``margin`` → otherwise reject ("better matches a different
           candidate"). This catches cross-matches.

    Returns:
        (is_match: bool, score: float|None, message: str)
    """
    profile = get_face_profile(certificate_id)
    if not profile:
        return False, None, "No face profile is enrolled for this certificate."

    target_embeddings = _load_embeddings(certificate_id)
    if target_embeddings is None or len(target_embeddings) == 0:
        return False, None, "Stored face embeddings are missing for this certificate."

    live_emb, err = _compute_embedding(_coerce_bytes(image_source))
    if live_emb is None:
        return False, None, err or "Could not extract a face from the live capture."

    # Best cosine similarity to the claimed certificate (using OpenCV's
    # canonical FaceRecognizerSF.match with FR_COSINE).
    target_score = _best_match_score(target_embeddings, live_emb)

    # Best cosine similarity to *any other* enrolled identity
    index = _load_index()
    best_other = -1.0
    best_other_cert = None
    for other_cid in index.keys():
        if other_cid == certificate_id:
            continue
        other_emb = _load_embeddings(other_cid)
        if other_emb is None:
            continue
        score = _best_match_score(other_emb, live_emb)
        if score > best_other:
            best_other = score
            best_other_cert = other_cid

    # 1) Absolute threshold — rejects unenrolled people
    if target_score < threshold:
        return False, target_score, (
            f"Face does not match the enrolled candidate "
            f"(similarity {target_score:.3f} < required {threshold:.3f}). "
            f"This may be a different person, or the photo quality is too low."
        )

    # 2) Cross-match guard — rejects if someone else is a meaningfully better match
    if best_other_cert is not None and (best_other - target_score) > margin:
        return False, target_score, (
            f"Captured face is a closer match to a different enrolled candidate "
            f"(claimed cert={target_score:.3f}, closest other={best_other:.3f}). "
            f"This certificate likely does not belong to the person in the photo."
        )

    detail = f"similarity {target_score:.3f} ≥ {threshold:.3f}"
    if best_other_cert is not None:
        detail += f", runner-up {best_other:.3f}"
    return True, target_score, f"Face matched ({detail})."


# ---------------------------------------------------------------------------
# Diagnostic CLI:  python -m application.utils.face_utils a.jpg b.jpg
# Prints the raw cosine score so you can calibrate FACE_MATCH_THRESHOLD on
# your actual webcam / lighting setup.
# ---------------------------------------------------------------------------

def _cli():
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m application.utils.face_utils <img1> <img2> [<img3> ...]")
        print("       Prints a cosine-similarity matrix between every pair.")
        sys.exit(1)
    paths = sys.argv[1:]
    embs = []
    for p in paths:
        with open(p, "rb") as f:
            data = f.read()
        emb, err = _compute_embedding(data)
        if emb is None:
            print(f"{p}: ERROR — {err}")
            sys.exit(2)
        embs.append((p, emb))
    print(f"\nThreshold: {FACE_MATCH_THRESHOLD:.3f}   Min face px: {FACE_MIN_PIXELS}\n")
    header = "                       " + "  ".join(f"{i+1:>6}" for i in range(len(embs)))
    print(header)
    for i, (pi, ei) in enumerate(embs):
        row = [f"{_cosine_match(ei, ej):.3f}" for _, ej in embs]
        print(f"{i+1}. {pi[:20]:<20}  " + "  ".join(f"{v:>6}" for v in row))
    print()


if __name__ == "__main__":
    _cli()
