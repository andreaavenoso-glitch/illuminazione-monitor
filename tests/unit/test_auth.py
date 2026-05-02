from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self) -> None:
        h = hash_password("supersecret-password")
        assert h != "supersecret-password"
        assert h.startswith("$2") or h.startswith("$argon")  # bcrypt prefix

    def test_verify_correct_password(self) -> None:
        h = hash_password("password123")
        assert verify_password("password123", h) is True

    def test_verify_wrong_password(self) -> None:
        h = hash_password("password123")
        assert verify_password("password124", h) is False

    def test_verify_against_garbage_hash(self) -> None:
        # passlib raises on totally invalid hashes — should swallow and return False.
        assert verify_password("anything", "not-a-real-hash") is False

    def test_hash_is_salted(self) -> None:
        a = hash_password("same-password")
        b = hash_password("same-password")
        assert a != b


class TestJwt:
    def test_roundtrip(self) -> None:
        uid = uuid4()
        token = create_access_token(user_id=uid, role="admin", email="x@x.it")
        payload = decode_access_token(token)
        assert payload["sub"] == str(uid)
        assert payload["role"] == "admin"
        assert payload["email"] == "x@x.it"
        assert payload["exp"] > payload["iat"]

    def test_expired_token_raises(self) -> None:
        token = create_access_token(
            user_id=uuid4(), role="viewer", email="x@x.it", expires_minutes=-1
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_tampered_signature_raises(self) -> None:
        token = create_access_token(user_id=uuid4(), role="viewer", email="x@x.it")
        # Flip a char in the signature segment to invalidate it.
        head, payload_seg, sig = token.split(".")
        tampered = ".".join([head, payload_seg, sig[:-1] + ("A" if sig[-1] != "A" else "B")])
        with pytest.raises(jwt.InvalidSignatureError):
            decode_access_token(tampered)

    def test_uses_configured_algorithm(self) -> None:
        token = create_access_token(user_id=uuid4(), role="viewer", email="x@x.it")
        # Header is base64url JSON; quick check the alg matches settings.
        header = jwt.get_unverified_header(token)
        assert header["alg"] == get_settings().jwt_algorithm

    def test_default_expiry_is_in_future(self) -> None:
        token = create_access_token(user_id=uuid4(), role="viewer", email="x@x.it")
        payload = decode_access_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        assert exp - datetime.now(tz=UTC) > timedelta(minutes=30)
