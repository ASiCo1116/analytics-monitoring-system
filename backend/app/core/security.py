import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from functools import cache

import bcrypt
import jwt

from app.core.config import settings
from app.models import Role

ALGORITHM = "HS256"
# bcrypt only uses the first 72 bytes; bcrypt 5.x raises ValueError beyond that
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str) -> bool:
    data = password.encode()
    # No valid password is this long (registration rejects it); answering
    # False keeps a long login attempt a plain 401 instead of a 500.
    if len(data) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(data, hashed_password.encode())


@cache
def _dummy_hash() -> str:
    return hash_password("not-a-real-password")


async def hash_password_async(password: str) -> str:
    """hash_password in a worker thread: bcrypt takes ~250 ms of CPU."""
    return await asyncio.to_thread(hash_password, password)


async def check_login_password(password: str, hashed: str | None) -> bool:
    """verify_password in a worker thread, also for unknown users.

    With no account (`hashed` is None) a dummy hash is checked, so a failed
    login takes the same time either way and does not reveal which
    usernames exist.
    """
    ok = await asyncio.to_thread(
        lambda: verify_password(password, hashed or _dummy_hash())
    )
    return ok and hashed is not None


def create_access_token(
    user_id: uuid.UUID,
    role: Role,
    expires_delta: timedelta | None = None,
) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        # Informational only: permissions are always checked against the
        # role stored in the database
        "role": role.value,
        "exp": datetime.now(UTC) + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    """Return the user id of a valid token.

    Raises jwt.InvalidTokenError for a bad signature, an expired token
    (ExpiredSignatureError is a subclass) or a malformed subject.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    try:
        return uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise jwt.InvalidTokenError("Invalid token subject") from exc
