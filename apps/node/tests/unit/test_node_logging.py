"""Node log redaction tests."""

from orbi_node.logging import redact_secrets


def test_credentials_authorization_and_content_are_redacted() -> None:
    jwt = "eyJheader.payload.signature"
    event = {
        "enrollment_secret": "enrollment-value",
        "access_token": jwt,
        "headers": {"Authorization": f"Bearer {jwt}"},
        "hf_token": "hf_private_token",
        "token": "generic_private_token",
        "prompt": "private prompt",
        "nested": {
            "messages": [{"role": "user", "content": "private prompt"}],
            "generated_output": "private response",
        },
        "text": "credential orbi_node_v1_LookupId1234_" + ("s" * 43),
    }
    redacted = redact_secrets(None, "info", event)
    rendered = repr(redacted)
    for secret in (
        "enrollment-value",
        jwt,
        "private prompt",
        "private response",
        "hf_private_token",
        "generic_private_token",
        "s" * 43,
    ):
        assert secret not in rendered
    assert redacted["headers"]["Authorization"] == "[REDACTED]"
