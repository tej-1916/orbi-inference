# ORBI Phase 1 — Verification Report

**Verification date:** 2026-06-29  
**Target runtime:** Python 3.12, PostgreSQL 16, Redis 7  
**Available verification runtime:** Python 3.13; Docker, PostgreSQL, Redis, and Gitleaks binaries
were not available in the build environment.

## Completed checks

- Python source and tests compile successfully.
- Ruff reports no lint or formatting errors.
- Pytest reports **20 passed and 1 skipped**.
- Bandit reports no findings in `apps/gateway/src`.
- `pip install -e .` succeeds and the package imports as `orbi_gateway`.
- Alembic successfully generates the complete PostgreSQL Phase 1 migration in offline SQL mode.
- The FastAPI lifespan starts with generated signing keys and `/health` returns HTTP 200.
- Docker Compose and GitHub workflow YAML files parse successfully.
- The bootstrap script creates `.env` and JWT files with owner-only mode `600`.
- A local pattern scan found no committed private-key blocks or complete ORBI credentials.

## Security checklist

- [x] Raw project API keys are never persisted.
- [x] API-key secrets use Argon2id plus a server-side pepper.
- [x] Random non-secret key IDs provide efficient lookup.
- [x] API-key comparison uses Argon2id's verification path.
- [x] Daily request limits are enforced durably under a PostgreSQL row lock.
- [x] Token budgets are reserved transactionally before queue insertion.
- [x] Worker JWTs are short-lived, scoped, rotatable, and revocable by JTI.
- [x] One-time worker enrollment tokens are hashed and consumed atomically.
- [x] PostgreSQL uniqueness is the idempotency correctness boundary.
- [x] Result submission atomically accepts at most one assigned-worker result.
- [x] Validation responses omit submitted prompts and credential values.
- [x] Request body size is bounded before JSON parsing.
- [x] Logs redact ORBI-shaped project, worker, and administrator credentials.

## Exit criteria

| Criterion | Status | Evidence or blocker |
|---|---|---|
| `docker compose up` starts full stack | **NOT VERIFIED** | Docker is unavailable in this environment |
| API key creation and authentication | **PARTIAL PASS** | Service and revoked-key tests pass; live PostgreSQL route test pending |
| Queued → assigned → completed lifecycle | **NOT VERIFIED LOCALLY** | Real PostgreSQL test exists and will run in GitHub Actions |
| Duplicate idempotency does not re-execute | **PARTIAL PASS** | DB constraint and service logic present; Docker-backed route run pending |
| Revoked worker JWT is rejected | **PASS** | Security dependency test passes |
| Over-budget request is rejected before queue | **PASS** | Unit tests and transactional reservation service pass |
| Expired lease is recovered | **NOT VERIFIED LOCALLY** | PostgreSQL implementation present; infrastructure run pending |
| Circuit opens after five failures | **PASS** | Unit test passes |
| Unit/security tests | **PASS** | 20 runnable tests pass |
| PostgreSQL integration tests | **SKIPPED LOCALLY** | One real integration test requires PostgreSQL |
| Bandit scan | **PASS** | Zero reported findings |
| Gitleaks scan | **NOT RUN LOCALLY** | Security workflow configured; local binary unavailable |

## Phase decision

**Ready for Phase 2: NO.**

Phase 2 remains blocked until the Docker-backed GitHub Actions run proves the migration, concurrent
`SKIP LOCKED` claim, result commitment, idempotency path, and lease recovery against PostgreSQL 16
and Redis 7. The dashboard, Colab worker, Kaggle worker, Hugging Face fallback, SDKs, and n8n flows
remain intentionally deferred.
