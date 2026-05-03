"""
One-shot cleanup utility: removes stored face profiles whose certificates no
longer exist on-chain (revoked, rejected, or never approved) and aren't in any
local Merkle batch store.

Run from the application/ directory:
    python cleanup_face_profiles.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from connection import contract
from utils.face_utils import _load_index, clear_face_profile
from utils.merkle_utils import _load_store


def main():
    index = _load_index()
    if not index:
        print("No face profiles enrolled.")
        return

    # Build the set of currently-valid cert IDs
    valid = set()
    try:
        valid.update(contract.functions.getAllCertificateIds().call())
    except Exception as exc:
        print(f"Warning: could not fetch approved certs ({exc})")
    try:
        valid.update(contract.functions.getAllPendingCertificateIds().call())
    except Exception as exc:
        print(f"Warning: could not fetch pending certs ({exc})")

    # Add batch certs (still alive if the batch wasn't rejected)
    for batch_id, batch_data in _load_store().items():
        for cert_id in batch_data.get("certificates", {}).keys():
            valid.add(cert_id)

    # Drop revoked certs from the valid set
    revoked = []
    for cert_id in list(valid):
        try:
            if contract.functions.isRevoked(cert_id).call():
                revoked.append(cert_id)
        except Exception:
            pass
    for cert_id in revoked:
        valid.discard(cert_id)

    orphans = [cid for cid in index.keys() if cid not in valid]
    if not orphans:
        print(f"All {len(index)} face profile(s) are bound to live certificates. Nothing to clean.")
        return

    print(f"Found {len(orphans)} orphan face profile(s):")
    for cid in orphans:
        owner = index[cid].get("owner_name", "<unknown>")
        print(f"  - {cid[:24]}...  ({owner})")

    confirm = input("\nDelete these profiles? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    for cid in orphans:
        clear_face_profile(cid)
    print(f"Removed {len(orphans)} face profile(s).")


if __name__ == "__main__":
    main()
