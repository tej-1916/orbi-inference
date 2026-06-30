# Phase 2 Milestone 1 — Deterministic Worker Runtime

The ORBI Node is an unprivileged, single-flight gateway client. It validates all `ORBI_NODE_`
settings before constructing its HTTP client, exchanges a short-lived one-time enrollment
credential for a scoped worker JWT, keeps that JWT in memory, renews it before expiry, reports
capabilities, polls one assignment at a time, and commits the exact assigned request ID.

## Runtime boundary

`InferenceRuntime` defines asynchronous `load`, `generate`, and `close` methods. The Milestone 1
implementation is deterministic: it hashes a canonical representation of the model and request
payload, never executes input, never calls a model or external service, and reports predictable
token counts. Constructor-only delay and failure controls support tests without exposing runtime
control fields to clients.

The runtime boundary is injected into `OrbiWorker`; model execution does not belong to the gateway
client or authentication components. Milestone 1 constructs `MockInferenceRuntime` in the node
entry point. The worker calls `load` before enrollment, `generate` only for an assigned request,
and `close` during shutdown.

The mock runtime canonicalizes the resolved model and request payload as sorted JSON, hashes that
representation with SHA-256, and returns a stable mock chat-completion envelope. It does not
interpret or execute prompt content.

## HTTP and authentication behavior

Every request uses a finite timeout. Network errors, HTTP 429, and HTTP 5xx use a bounded retry
budget. Backoff is exponential with jitter; `Retry-After` is honored within the configured safety
ceiling. Other 4xx responses are permanent. A 401 causes one controlled re-enrollment attempt,
then a clean worker shutdown when the consumed enrollment credential cannot be reused.

## Security boundary

The node receives no PostgreSQL URL, Redis URL, user API key, JWT signing key, or administrator
credential. Its logger recursively redacts authorization, enrollment, JWT, prompt, message, and
generated-output fields. The Docker image runs as the non-root `orbi-node` user.

On shutdown, polling stops first, the active inference is allowed to finish, a draining heartbeat
is attempted, the runtime unloads, the in-memory JWT is cleared, and the HTTP client closes.

The container image creates `orbi-node` as UID `10002`; the running Compose node was verified as
UID/GID `10002`.

## Configuration

Milestone 1 reads only typed `ORBI_NODE_` settings. The Compose node supplies:

- Gateway URL
- Worker name and provider type
- One-time enrollment ID and secret
- Supported model IDs
- Heartbeat, polling, and HTTP timeout intervals
- Log level

The node configuration does not accept a PostgreSQL URL, Redis URL, user API key, gateway JWT
signing key, or administrator token.

## Verified lifecycle

The full PostgreSQL and Redis test run passed with `42 passed`. Its integration coverage exercised
the following sequence:

1. Create isolated gateway configuration and database records.
2. Enroll the node using a one-time credential.
3. Claim the queued request through the gateway worker API.
4. Run `MockInferenceRuntime`.
5. Submit the result for the exact assigned request ID.
6. Verify the durable request status is `COMPLETED` with token counts and the deterministic result.
7. Close the node and unload the runtime.

Ruff passed. Bandit reported zero findings and zero skipped files. Docker Compose configuration
validation passed; PostgreSQL, Redis, gateway, and node were visibly running; and the gateway
health endpoint passed. All five GitHub Actions checks passed.

## Milestone boundary

No Gemma model, Transformers dependency, quantization backend, hosted fallback, notebook,
streaming transport, or automatic failover is part of Milestone 1. The deterministic mock runtime
remains the only implemented inference runtime at this stage.
