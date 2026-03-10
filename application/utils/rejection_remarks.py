"""
Storage for certificate rejection remarks.

When an admin rejects a certificate, the remarks and original certificate info
are saved here so the institute can see why it was rejected and reapply.
"""
import json
import os
from datetime import datetime

REMARKS_FILE = os.path.join(os.path.dirname(__file__), "..", "rejection_remarks.json")


def _load():
    if os.path.exists(REMARKS_FILE):
        with open(REMARKS_FILE, "r") as f:
            return json.load(f)
    return {}


def _save(data):
    with open(REMARKS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def save_rejection(certificate_id, remarks, admin_email, cert_info):
    """
    Store rejection remarks for a certificate.

    cert_info should contain the original certificate fields so the institute
    can see them when reapplying:
        uid, candidate_name, course_name, org_name, grade, institute_email, ipfs_hash
    """
    data = _load()
    data[certificate_id] = {
        "remarks": remarks,
        "admin_email": admin_email,
        "rejected_at": datetime.now().isoformat(),
        "cert_info": cert_info,
    }
    _save(data)


def get_rejection(certificate_id):
    """Return rejection info dict or None if not rejected."""
    return _load().get(certificate_id)


def get_rejections_for_institute(institute_email):
    """Return all rejections for a given institute email."""
    data = _load()
    return {
        cid: info
        for cid, info in data.items()
        if info.get("cert_info", {}).get("institute_email") == institute_email
    }


def remove_rejection(certificate_id):
    """Remove a rejection record (e.g. after successful reapply)."""
    data = _load()
    if certificate_id in data:
        del data[certificate_id]
        _save(data)
