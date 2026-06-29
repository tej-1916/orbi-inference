"""API-key service unit tests."""

from datetime import UTC, datetime, timedelta

from orbi_gateway.services.api_keys import APIKeyService

PEPPER = "p" * 48


def test_api_key_generation_round_trip_verifies_secret() -> None:
    service = APIKeyService(PEPPER)
    generated = service.generate("test")
    parsed = service.parse(generated.raw_key)
    assert parsed is not None
    environment, key_id, secret = parsed
    assert environment == "test"
    assert key_id == generated.key_id
    assert service.verify_secret(secret, generated.secret_hash)


def test_api_key_verification_with_wrong_secret_returns_false() -> None:
    service = APIKeyService(PEPPER)
    generated = service.generate("live")
    assert not service.verify_secret("wrong-secret-value" * 3, generated.secret_hash)


def test_api_key_lookup_identifier_is_not_shared_static_prefix() -> None:
    service = APIKeyService(PEPPER)
    first = service.generate("live")
    second = service.generate("live")
    assert first.key_id != second.key_id
    assert first.display_prefix != second.display_prefix


def test_api_key_record_activity_rejects_revoked_and_expired() -> None:
    now = datetime.now(UTC)
    assert APIKeyService.is_record_active(now + timedelta(minutes=1), None)
    assert not APIKeyService.is_record_active(now - timedelta(seconds=1), None)
    assert not APIKeyService.is_record_active(None, now)
