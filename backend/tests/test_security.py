import uuid
from datetime import timedelta

import jwt
import pytest

from app.core import security
from app.core.config import settings
from app.core.security import (
    check_login_password,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_password_async,
    verify_password,
)
from app.models import Role


def test_hash_and_verify_password():
    hashed = hash_password("Password123")

    assert hashed != "Password123"
    assert verify_password("Password123", hashed)
    assert not verify_password("wrong-password", hashed)


async def test_async_hash_and_login_check():
    hashed = await hash_password_async("Password123")

    assert await check_login_password("Password123", hashed)
    assert not await check_login_password("wrong-password", hashed)


async def test_unknown_user_still_runs_bcrypt(monkeypatch):
    # A missing account must cost a bcrypt check too, or the response
    # time would reveal which usernames exist
    calls = []
    real_verify = security.verify_password
    monkeypatch.setattr(
        security,
        "verify_password",
        lambda password, hashed: (
            calls.append(hashed) or real_verify(password, hashed)
        ),
    )

    assert not await check_login_password("Password123", None)
    assert len(calls) == 1


def test_password_over_72_bytes_is_rejected_without_error():
    hashed = hash_password("Password123")

    # 73 bytes in UTF-8; bcrypt 5 itself would raise ValueError
    assert not verify_password("a" * 73, hashed)
    # Multi-byte characters count in bytes: 25 x 3 bytes = 75 bytes
    assert not verify_password("密" * 25, hashed)


def test_token_round_trip():
    user_id = uuid.uuid7()

    token = create_access_token(user_id, Role.user)

    assert decode_access_token(token) == user_id


def test_expired_token_is_rejected():
    token = create_access_token(
        uuid.uuid7(), Role.user, expires_delta=timedelta(seconds=-1)
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_is_rejected():
    token = create_access_token(uuid.uuid7(), Role.user)
    forged = jwt.encode(
        jwt.decode(token, options={"verify_signature": False}),
        "another-secret-that-is-at-least-32-bytes",
        algorithm="HS256",
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged)


def test_token_with_non_uuid_subject_is_rejected():
    token = create_access_token(uuid.uuid7(), Role.user)
    payload = jwt.decode(token, options={"verify_signature": False})
    payload["sub"] = "not-a-uuid"
    bad = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(bad)
