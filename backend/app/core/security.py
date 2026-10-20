import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from starlette.concurrency import run_in_threadpool

# argon2id with library defaults (RFC 9106 low-memory profile).
_hasher = PasswordHasher()
# Verified against when a username does not exist, so response timing does not reveal it.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


async def hash_password(password: str) -> str:
    # Hashing is deliberately CPU-heavy; keep it off the event loop.
    return await run_in_threadpool(_hasher.hash, password)


async def verify_password(password: str, password_hash: str | None) -> bool:
    def _verify() -> bool:
        try:
            return _hasher.verify(password_hash or _DUMMY_HASH, password) and bool(password_hash)
        except (VerificationError, InvalidHashError):
            return False

    return await run_in_threadpool(_verify)


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Session tokens are stored hashed, so a database leak does not leak live sessions."""
    return hashlib.sha256(token.encode()).hexdigest()
