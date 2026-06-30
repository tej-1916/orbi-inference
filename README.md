# ORBI

> Run open models anywhere. Serve them through one API.

ORBI is an open-source distributed LLM inference control plane. The control plane provides the
secure API gateway, worker registry, durable PostgreSQL queue, idempotency boundary, budgets, and
short-lived worker identity. Phase 2 Milestone 1 adds a deterministic local worker runtime.

## Current status

This branch contains the **Phase 2 Milestone 1 deterministic worker**. It intentionally does not
include a real model adapter, dashboard, Colab notebook, Kaggle worker, managed-provider fallback,
or SDK.

Milestone 1 verification is complete:

- Ruff passed.
- The full PostgreSQL and Redis test run passed: `42 passed`.
- Bandit reported zero findings and zero skipped files.
- Docker Compose configuration validation passed.
- PostgreSQL, Redis, gateway, and node containers ran together, and the gateway health endpoint
  passed.
- The node container ran as UID/GID `10002`.
- The gateway-to-node-to-mock-runtime-to-result lifecycle passed.
- All five GitHub Actions checks passed.

See [the Phase 2 build confirmation](docs/phase-2-build-confirmation.md) for the exact verified
results and [the worker runtime guide](docs/phase-2-worker-runtime.md) for its architecture and
operating boundary.

## Security model

- Raw API keys are displayed once and never persisted.
- API-key secrets are protected with Argon2id and a server-side pepper.
- A random non-secret key ID is used for database lookup.
- PostgreSQL uniqueness is the source of truth for idempotency.
- Worker JWTs are short-lived and scoped.
- ORBI provides at-least-once execution with single-result commitment; it does not claim magical
  exactly-once execution across failed inference workers.

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python scripts/bootstrap-dev.py
# Save the one-time admin token printed by the command.
docker compose --env-file .env -f deploy/docker-compose.yml up --build
```

Health check:

```bash
curl http://localhost:8000/health
```

See `docs/phase-1-decisions.md` before contributing.

## Bootstrap the control plane

Keep the one-time administrator token in your shell session, not in the repository:

```bash
export ORBI_ADMIN_TOKEN='paste-the-token-printed-by-bootstrap-dev.py'
```

Create a project:

```bash
curl -sS http://localhost:8000/admin/projects \
  -H "Authorization: Bearer $ORBI_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "ORBI Development",
    "slug": "orbi-development",
    "owner_id": "00000000-0000-0000-0000-000000000001"
  }'
```

Then create a model alias, an API key, and a one-time worker enrollment token through the
administrative endpoints documented in `docs/api-reference.md`. After the `orbi_node_v1_` prefix,
use exactly 12 characters for `ORBI_NODE_ENROLLMENT_ID` and the remaining 43 characters for
`ORBI_NODE_ENROLLMENT_SECRET`. See `docs/phase-2-worker-runtime.md`.
