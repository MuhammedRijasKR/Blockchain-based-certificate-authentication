"""Per-institute Ganache signer mapping.

Each institute is bound to a unique Ganache account at registration time. The
mapping is persisted so subsequent logins reuse the same signer, which the
on-chain contract enforces via ``msg.sender == institutes[email].signer``.

Admin signer accounts (configured in ``admin_config.ADMIN_SIGNER_EMAILS``) are
reserved and never handed to institutes.
"""

import json
import os
from pathlib import Path

from connection import w3
from utils.admin_config import ADMIN_SIGNER_EMAILS

_BASE = Path(__file__).resolve().parent.parent
_STORE = _BASE / "institute_signers.json"


def _load():
    if not _STORE.exists():
        return {}
    try:
        with open(_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    tmp = _STORE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _STORE)


def _reserved_admin_addresses():
    accounts = w3.eth.accounts
    reserved = set()
    for i, _email in enumerate(ADMIN_SIGNER_EMAILS):
        if i < len(accounts):
            reserved.add(accounts[i].lower())
    return reserved


def get_institute_signer(email):
    """Return the bound signer address for ``email``.

    Allocates the next free Ganache account on first call. Returns ``None`` if
    every available account is already taken.
    """
    email = (email or "").strip().lower()
    if not email:
        return None

    data = _load()
    current_accounts = {addr.lower() for addr in w3.eth.accounts}

    if email in data:
        signer = data[email]
        if signer and signer.lower() in current_accounts:
            return signer

        # Ganache was likely restarted/reseeded. Do not reuse an address that
        # the current node no longer controls; allocate a fresh current account.
        del data[email]
        _save(data)

    used = {
        addr.lower()
        for addr in data.values()
        if addr and addr.lower() in current_accounts
    }
    used.update(_reserved_admin_addresses())
    for addr in w3.eth.accounts:
        if addr.lower() not in used:
            data[email] = addr
            _save(data)
            return addr
    return None


def lookup_institute_signer(email):
    """Return the bound signer address without allocating a new one."""
    signer = _load().get((email or "").strip().lower())
    if signer and signer.lower() in {addr.lower() for addr in w3.eth.accounts}:
        return signer
    return None
