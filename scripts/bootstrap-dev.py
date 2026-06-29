#!/usr/bin/env python3
"""Create an uncommitted local `.env`, JWT keypair, and one bootstrap admin token."""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from argon2 import PasswordHasher
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
SECRETS_DIR = ROOT / "secrets"
PRIVATE_KEY_PATH = SECRETS_DIR / "orbi_jwt_private.pem"
PUBLIC_KEY_PATH = SECRETS_DIR / "orbi_jwt_public.pem"


def secure_write(path: Path, content: str) -> None:
    """Create a file with owner-only permissions and refuse silent overwrites."""
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def main() -> None:
    """Generate development-only secrets without persisting the raw admin token."""
    if ENV_PATH.exists() or PRIVATE_KEY_PATH.exists() or PUBLIC_KEY_PATH.exists():
        raise SystemExit(
            "Bootstrap files already exist. Move or delete .env and secrets/ "
            "intentionally before rerunning."
        )

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    api_key_pepper = secrets.token_urlsafe(48)
    worker_pepper = secrets.token_urlsafe(48)
    admin_pepper = secrets.token_urlsafe(48)
    postgres_password = secrets.token_urlsafe(32)
    admin_token = f"orbi_admin_v1_{secrets.token_urlsafe(32)}"
    admin_hash = PasswordHasher().hash(f"{admin_token}:{admin_pepper}")

    env_content = f"""ORBI_ENVIRONMENT=development
ORBI_LOG_LEVEL=INFO
ORBI_HOST_UID={os.getuid()}
ORBI_HOST_GID={os.getgid()}
ORBI_POSTGRES_PASSWORD='{postgres_password}'
ORBI_DATABASE_URL='postgresql+asyncpg://orbi:{postgres_password}@postgres:5432/orbi'
ORBI_REDIS_URL='redis://redis:6379/0'
ORBI_API_KEY_PEPPER='{api_key_pepper}'
ORBI_WORKER_ENROLLMENT_PEPPER='{worker_pepper}'
ORBI_JWT_PRIVATE_KEY_PATH='/run/secrets/orbi_jwt_private.pem'
ORBI_JWT_PUBLIC_KEY_PATH='/run/secrets/orbi_jwt_public.pem'
ORBI_JWT_ISSUER='orbi-core'
ORBI_JWT_AUDIENCE='orbi-worker'
ORBI_WORKER_TOKEN_TTL_SECONDS=3600
ORBI_ADMIN_TOKEN_HASH='{admin_hash}'
ORBI_ADMIN_TOKEN_PEPPER='{admin_pepper}'
ORBI_RATE_LIMIT_RPM_DEFAULT=60
ORBI_MAX_REQUEST_BODY_BYTES=1048576
ORBI_REQUEST_WAIT_TIMEOUT_SECONDS=60
ORBI_WORKER_LEASE_SECONDS=120
ORBI_LEASE_RECOVERY_INTERVAL_SECONDS=30
ORBI_CIRCUIT_FAILURE_THRESHOLD=5
ORBI_CIRCUIT_COOLDOWN_SECONDS=120
"""

    secure_write(PRIVATE_KEY_PATH, private_pem)
    secure_write(PUBLIC_KEY_PATH, public_pem)
    secure_write(ENV_PATH, env_content)

    print("ORBI development configuration created.")
    print("Store this bootstrap admin token now; it will not be written to disk again:")
    print(admin_token)


if __name__ == "__main__":
    main()
