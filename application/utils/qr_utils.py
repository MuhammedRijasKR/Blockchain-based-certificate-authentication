"""QR code generation and decoding helpers.

QR payload for BlockCert is the bare certificate_id string. Verifier scans
the QR image, extracts the cert_id, and routes to the existing
Certificate ID verification flow.
"""
from io import BytesIO

import qrcode
import qrcode.constants
import numpy as np
import cv2


def make_qr_png_bytes(data: str, box_size: int = 8, border: int = 2) -> bytes:
    """Return a PNG byte string of the QR code encoding `data`.

    Uses high error correction so the code remains scannable even if the
    PDF is printed and partially smudged.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_qr_image_buffer(data: str) -> BytesIO:
    """Return a BytesIO of a PNG QR for embedding in ReportLab PDFs."""
    buf = BytesIO(make_qr_png_bytes(data))
    buf.seek(0)
    return buf


def decode_qr_from_bytes(image_bytes: bytes) -> str | None:
    """Decode a QR code from raw image bytes. Returns the decoded string
    or None if no QR could be read.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    detector = cv2.QRCodeDetector()
    data, _points, _straight = detector.detectAndDecode(img)
    if data:
        return data.strip()
    return None
