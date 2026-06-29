"""Credential-redaction unit tests."""

from orbi_gateway.logging import redact_secrets


def test_logging_redacts_api_and_worker_tokens() -> None:
    event = {
        "api_key": "orbi_live_v1_lookupId123_secretValueSecretValueSecretValue123",
        "nested": {"worker": "orbi_node_v1_lookupId123_secretValueSecretValueSecretValue123"},
    }
    redacted = redact_secrets(None, "info", event)
    assert redacted["api_key"] == "[REDACTED_ORBI_TOKEN]"
    assert redacted["nested"]["worker"] == "[REDACTED_ORBI_TOKEN]"
