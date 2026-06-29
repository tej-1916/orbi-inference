"""One-time worker enrollment and short-lived scoped JWT creation and verification."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


@dataclass(frozen=True, slots=True)
class GeneratedEnrollmentToken:
    raw_token: str
    token_id: str
    secret_hash: str


class WorkerEnrollmentService:
    """Create one-time worker enrollment tokens without storing their raw values."""

    def __init__(self, pepper: str, password_hasher: PasswordHasher | None = None) -> None:
        if len(pepper.encode()) < 32:
            raise ValueError("worker enrollment pepper must contain at least 32 bytes")
        self._pepper = pepper
        self._hasher = password_hasher or PasswordHasher()

    def generate(self) -> GeneratedEnrollmentToken:
        token_id = secrets.token_urlsafe(9)
        secret = secrets.token_urlsafe(32)
        return GeneratedEnrollmentToken(
            raw_token=f"orbi_node_v1_{token_id}_{secret}",
            token_id=token_id,
            secret_hash=self._hasher.hash(f"{secret}:{self._pepper}"),
        )

    def parse_and_verify(self, raw_token: str, expected_hash: str) -> str | None:
        prefix = "orbi_node_v1_"
        if not raw_token.startswith(prefix):
            return None
        remainder = raw_token.removeprefix(prefix)
        if len(remainder) != 56 or remainder[12] != "_":
            return None
        token_id, secret = remainder[:12], remainder[13:]
        try:
            if self._hasher.verify(expected_hash, f"{secret}:{self._pepper}"):
                return token_id
        except (VerifyMismatchError, InvalidHashError):
            pass
        return None


class WorkerJWTService:
    """Issue and verify RS256 worker tokens loaded from mounted key files."""

    def __init__(
        self,
        private_key_path: Path,
        public_key_path: Path,
        issuer: str,
        audience: str,
        ttl_seconds: int,
    ) -> None:
        self._private_key = private_key_path.read_text(encoding="utf-8")
        self._public_key = public_key_path.read_text(encoding="utf-8")
        self._issuer = issuer
        self._audience = audience
        self._ttl = ttl_seconds

    def issue(self, worker_id: UUID) -> tuple[str, str]:
        now = datetime.now(UTC)
        jti = str(uuid4())
        claims = {
            "sub": str(worker_id),
            "jti": jti,
            "scope": [
                "worker:heartbeat",
                "worker:pull",
                "worker:result",
                "worker:error",
                "worker:renew",
            ],
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=self._ttl),
            "iss": self._issuer,
            "aud": self._audience,
        }
        return jwt.encode(claims, self._private_key, algorithm="RS256"), jti

    def verify(self, token: str) -> dict[str, object]:
        claims = jwt.decode(
            token,
            self._public_key,
            algorithms=["RS256"],
            audience=self._audience,
            issuer=self._issuer,
            options={"require": ["sub", "jti", "scope", "exp", "iat", "nbf"]},
        )
        return dict(claims)
