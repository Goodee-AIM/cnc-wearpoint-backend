"""Generate a PBKDF2 hash without placing the operator password in shell history."""

import getpass
import hashlib
import secrets


if __name__ == "__main__":
    password = getpass.getpass("Prediction operator password: ")
    if len(password) < 16:
        raise SystemExit("Choose an operator password of at least 16 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    print(f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}")
