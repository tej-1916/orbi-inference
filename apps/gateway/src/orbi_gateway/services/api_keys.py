"""Create and verify API keys without ever persisting the raw credential."""

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_KEY_RE = re.compile(r"^orbi_(live|test)_v1_([A-Za-z0-9_-]{12})_([A-Za-z0-9_-]{43})$")


@dataclass(frozen=True, slots=True)
class GeneratedAPIKey:
    raw_key: str
    key_id: str
    display_prefix: str
    secret_hash: str
    environment: str


class APIKeyService:
    """Use random lookup IDs and Argon2id-protected secrets for API credentials."""

    def __init__(self, pepper: str, password_hasher: PasswordHasher | None = None) -> None:
        if len(pepper.encode()) < 32:
            raise ValueError("API key pepper must contain at least 32 bytes")
        self._pepper = pepper
        self._hasher = password_hasher or PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=2,
            hash_len=32,
            salt_len=16,
        )

    def generate(self, environment: str) -> GeneratedAPIKey:
        """Generate one API key; callers must return the raw value exactly once."""
        if environment not in {"live", "test"}:
            raise ValueError("environment must be 'live' or 'test'")
        key_id = secrets.token_urlsafe(9)
        secret = secrets.token_urlsafe(32)
        raw_key = f"orbi_{environment}_v1_{key_id}_{secret}"
        secret_hash = self._hasher.hash(self._peppered(secret))
        return GeneratedAPIKey(
            raw_key=raw_key,
            key_id=key_id,
            display_prefix=f"orbi_{environment}_v1_{key_id}",
            secret_hash=secret_hash,
            environment=environment,
        )

    def parse(self, raw_key: str) -> tuple[str, str, str] | None:
        """Return environment, non-secret key ID, and secret for a structurally valid key."""
        match = _KEY_RE.fullmatch(raw_key)
        if match is None:
            return None
        return match.group(1), match.group(2), match.group(3)

    def verify_secret(self, secret: str, stored_hash: str) -> bool:
        """Verify an API-key secret using Argon2id's constant-time verification path."""
        try:
            return self._hasher.verify(stored_hash, self._peppered(secret))
        except (VerifyMismatchError, InvalidHashError):
            return False

    @staticmethod
    def is_record_active(expires_at: datetime | None, revoked_at: datetime | None) -> bool:
        """Reject revoked or expired records."""
        if revoked_at is not None:
            return False
        return expires_at is None or expires_at > datetime.now(UTC)

    def _peppered(self, secret: str) -> str:
        return f"{secret}:{self._pepper}"
