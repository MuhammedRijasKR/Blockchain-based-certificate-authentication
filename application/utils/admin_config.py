"""Admin account configuration for the 2-of-3 approval flow."""

# Order matters: these emails map to Ganache accounts 0, 1, and 2.
ADMIN_SIGNER_EMAILS = [
    "adm@bc.com",
    "adm3@bc.com",
    "adm2@bc.com",
]

# Only these emails can self-register as admin accounts.
ADMIN_EMAILS = ADMIN_SIGNER_EMAILS
