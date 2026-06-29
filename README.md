# ORBI

> Run open models anywhere. Serve them through one API.

ORBI is an open-source distributed LLM inference control plane. Phase 1 establishes the secure
API gateway, worker registry, durable PostgreSQL queue, idempotency boundary, budgets, and
short-lived worker identity.

## Current status

This repository is at **v0.1 Phase 1 foundation**. It intentionally does not include a dashboard,
Colab notebook, Kaggle worker, managed-provider fallback, or SDK.

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
administrative endpoints documented in `docs/api-reference.md`. The Phase 1 repository contains
the control plane only; Colab, Kaggle, and local inference-node runtimes begin in Phase 2.
