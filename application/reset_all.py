"""
reset_all.py  -  Wipe all BlockCert local state for a clean restart.

This will:
  1. Delete every certificate's face profile (face_profiles/, face_profiles.json).
  2. Delete encryption keys, merkle proofs, bloom filter, rejection remarks,
     last UID counter, and cached Streamlit auth.
  3. Optionally wipe per-institute RSA key folders under application/keys/.
  4. Optionally re-deploy the smart contract via ``truffle migrate --reset``
     (this gives you a fresh on-chain certificate registry).

It does NOT touch:
  - .env / serviceAccountKey.json / requirements.txt
  - Firebase Auth users (manage those in the Firebase console)
  - Files already pinned to Pinata (manually unpin via the dashboard if needed)

Usage:
    python application/reset_all.py            # interactive, prompts for confirmation
    python application/reset_all.py --yes      # no prompts
    python application/reset_all.py --yes --keep-keys   # keep RSA keys
    python application/reset_all.py --yes --no-truffle  # skip contract redeploy
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "application"

STATE_FILES = [
    APP_DIR / "face_profiles.json",
    APP_DIR / "encryption_keys.json",
    APP_DIR / "merkle_proofs.json",
    APP_DIR / "bloom_filter.json",
    APP_DIR / "rejection_remarks.json",
    APP_DIR / "batch_rejection_remarks.json",
    APP_DIR / "last_uid.json",
    APP_DIR / ".streamlit_auth.json",
]

STATE_DIRS = [
    APP_DIR / "face_profiles",
]

OPTIONAL_DIRS_KEYS = [
    APP_DIR / "keys",  # per-institute RSA key folders
]


def _rm_file(path: Path):
    if path.exists():
        path.unlink()
        print(f"  removed file   {path.relative_to(PROJECT_ROOT)}")


def _rm_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
        print(f"  removed dir    {path.relative_to(PROJECT_ROOT)}")


def _truffle_reset():
    print("\n[2/2] Re-deploying smart contracts (truffle migrate --reset)…")
    cmd = ["truffle", "migrate", "--reset"]
    try:
        proc = subprocess.run(
            cmd, cwd=PROJECT_ROOT, shell=True, check=False,
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        print("  truffle not found on PATH — skipping contract redeploy.")
        return False
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print("  truffle migrate failed.")
        return False
    print("  contracts redeployed successfully.")
    return True


def _refresh_deployment_config():
    """Re-read build/contracts/Certification.json and sync deployment_config.json."""
    build_path = PROJECT_ROOT / "build" / "contracts" / "Certification.json"
    cfg_path = PROJECT_ROOT / "deployment_config.json"
    if not build_path.exists():
        return
    try:
        with open(build_path, "r", encoding="utf-8") as f:
            artifact = json.load(f)
        networks = artifact.get("networks", {})
        if not networks:
            return
        # Pick the most recently deployed network
        latest_net = max(networks.items(), key=lambda kv: kv[1].get("updated_at", 0))
        addr = latest_net[1].get("address")
        if not addr:
            return
        cfg = {}
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["contract_address"] = addr
        cfg["network_id"] = latest_net[0]
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        print(f"  updated deployment_config.json with new address {addr}")
    except Exception as exc:
        print(f"  could not update deployment_config.json: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Wipe BlockCert local state.")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="skip the confirmation prompt")
    parser.add_argument("--keep-keys", action="store_true",
                        help="do not delete application/keys/ (per-institute RSA keys)")
    parser.add_argument("--no-truffle", action="store_true",
                        help="skip 'truffle migrate --reset'")
    args = parser.parse_args()

    print("BlockCert reset")
    print("===============")
    print("This will delete:")
    for p in STATE_FILES + STATE_DIRS:
        print(f"  - {p.relative_to(PROJECT_ROOT)}")
    if not args.keep_keys:
        for p in OPTIONAL_DIRS_KEYS:
            print(f"  - {p.relative_to(PROJECT_ROOT)}  (RSA institute keys)")
    if not args.no_truffle:
        print("  - and re-deploy the smart contract (truffle migrate --reset)")
    print()

    if not args.yes:
        ans = input("Type 'RESET' to confirm: ").strip()
        if ans != "RESET":
            print("Aborted.")
            return 1

    print("\n[1/2] Deleting local state…")
    for f in STATE_FILES:
        _rm_file(f)
    for d in STATE_DIRS:
        _rm_dir(d)
    if not args.keep_keys:
        for d in OPTIONAL_DIRS_KEYS:
            _rm_dir(d)

    if not args.no_truffle:
        if _truffle_reset():
            _refresh_deployment_config()

    print("\nDone. Restart Streamlit (and Ganache if it was reset) before issuing certificates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
