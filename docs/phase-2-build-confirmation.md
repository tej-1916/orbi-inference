# ORBI Phase 2 — Build Confirmation

## Milestone 1 objective

Build the first ORBI Node runtime using deterministic mock inference.

## Verified implementation

- Worker configuration
- Enrollment-token authentication
- Challenge confirmation
- Scoped worker JWT storage in memory
- JWT renewal
- Heartbeat loop
- Hardware capability discovery
- Request polling
- Deterministic mock inference
- Result submission
- Error reporting
- Graceful shutdown
- Docker worker container
- Unit and integration tests

The implementation is recorded in these commits:

- `a159e84` — `feat(node): add deterministic worker runtime`
- `4b5f93e` — `fix(compose): connect local worker to gateway`
- `30b7b40` — `fix(ci): isolate node lifecycle configuration`

## Verification results

Verified on 2026-06-30 from `feat/phase-2-worker-runtime`:

| Check | Result |
| --- | --- |
| Ruff | Passed |
| Full tests using PostgreSQL and Redis | `42 passed`, with one third-party deprecation warning |
| Bandit | Zero findings and zero files skipped |
| Docker Compose configuration | Valid |
| Gateway health endpoint | Passed; returned `{"status":"ok","service":"orbi-gateway"}` |
| PostgreSQL container | Running and healthy |
| Redis container | Running and healthy |
| Gateway container | Running and healthy |
| Node container | Running |
| Node container identity | UID/GID `10002` (`orbi-node`) |
| Gateway → node → mock runtime → result lifecycle | Passed |
| GitHub Actions | All five checks passed |

The five passing GitHub checks were:

- `CodeQL`
- `security/codeql`
- `security/filesystem-scan`
- `security/secret-scan`
- `test/gateway`

The full test run used the local PostgreSQL service on port `55432`, Redis on port `56379`, and
the isolated Redis database selected for tests. The lifecycle integration test created its own
ephemeral signing key pair and gateway configuration, enrolled a node, claimed a queued request,
ran deterministic mock inference, submitted the result, and verified that the stored request
reached `COMPLETED`.

Bandit scanned `apps/gateway/src` and `apps/node/src`. It reported zero issues at every severity
and confidence level, zero skipped lines, zero issues disabled with `#nosec`, and zero skipped
files.

Docker Compose rendered to a non-empty configuration before service status was inspected. Service
status showed PostgreSQL, Redis, gateway, and node running; PostgreSQL, Redis, and gateway were
healthy. A direct request to `http://localhost:8000/health` passed.

## Deferred scope

- Gemma model loading
- Transformers
- bitsandbytes
- Colab notebook
- Kaggle notebook
- Hugging Face fallback
- Streaming inference
- n8n
- Dashboard
- Production GPU providers

No real model was loaded or executed in Milestone 1.

## Security boundaries

- No database or Redis credentials inside workers
- No user API keys passed to workers
- No plaintext worker secrets in logs
- Enrollment credentials are one-time and short-lived
- Worker JWTs remain memory-only where possible
- Every HTTP request uses a timeout
- Results may be submitted only for assigned requests
- Graceful shutdown stops request claiming before exit

The Docker worker runs as the unprivileged `orbi-node` user with UID/GID `10002`. Enrollment
credentials and worker JWTs are not written to these documents.
