"""Admin account configuration.

``ADMIN_SIGNER_EMAILS`` are the on-chain signers (mapped 1:1 to Ganache
accounts 0..N-1) used for the M-of-N approval flow.

``ADMIN_EMAILS`` are the addresses allowed to **log in** as admin. Keeping the
two lists separate makes it possible to add read-only admin reviewers without
giving them on-chain signing power, or to rotate signers without touching the
auth allowlist.
"""

# Order matters: these emails map to Ganache accounts 0, 1, and 2.
ADMIN_SIGNER_EMAILS = [
    "adm@bc.com",
    "adm3@bc.com",
    "adm2@bc.com",
]

# Anyone who can log in as ``role=admin``. Includes all signers by default; add
# additional entries here for reviewers that should not have on-chain power.
ADMIN_EMAILS = list(ADMIN_SIGNER_EMAILS)
