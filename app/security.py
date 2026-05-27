from __future__ import annotations

import hashlib
import hmac
import secrets


ITERATIONS = 260_000
ALGORITHM = "sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(ALGORITHM, password.encode("utf-8"), salt.encode("ascii"), ITERATIONS)
    return f"pbkdf2_{ALGORITHM}${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        scheme, iterations, salt, expected = hashed_password.split("$", 3)
        if scheme != f"pbkdf2_{ALGORITHM}":
            return False
        digest = hashlib.pbkdf2_hmac(
            ALGORITHM,
            password.encode("utf-8"),
            salt.encode("ascii"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False
