"""Worker enrollment and JWT unit tests."""

from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from argon2 import PasswordHasher
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from orbi_gateway.services.worker_tokens import WorkerEnrollmentService, WorkerJWTService

PEPPER = "w" * 48


def test_worker_enrollment_token_round_trip_verifies() -> None:
    service = WorkerEnrollmentService(PEPPER, PasswordHasher(time_cost=1, memory_cost=8192))
    generated = service.generate()
    assert (
        service.parse_and_verify(generated.raw_token, generated.secret_hash) == generated.token_id
    )
    assert service.parse_and_verify(generated.raw_token + "x", generated.secret_hash) is None


def test_worker_enrollment_parser_handles_base64url_underscores() -> None:
    service = WorkerEnrollmentService(PEPPER, PasswordHasher(time_cost=1, memory_cost=8192))
    token_id = "abc_defghijk"  # noqa: S105
    secret = "_" * 43
    stored_hash = service._hasher.hash(f"{secret}:{PEPPER}")  # noqa: SLF001
    raw_token = f"orbi_node_v1_{token_id}_{secret}"
    assert service.parse_and_verify(raw_token, stored_hash) == token_id


def test_worker_jwt_contains_only_expected_worker_scopes(tmp_path: Path) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    service = WorkerJWTService(
        private_path,
        public_path,
        issuer="orbi-core-test",
        audience="orbi-worker-test",
        ttl_seconds=600,
    )
    token, _ = service.issue(uuid4())
    claims = service.verify(token)
    assert set(claims["scope"]) == {
        "worker:heartbeat",
        "worker:pull",
        "worker:result",
        "worker:error",
        "worker:renew",
    }
    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(
            token,
            public_path.read_text(),
            algorithms=["RS256"],
            audience="wrong-audience",
            issuer="orbi-core-test",
        )
