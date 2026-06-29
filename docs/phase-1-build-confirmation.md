# ORBI Phase 1 — Build Confirmation

**Project:** ORBI (`orbi-inference`)  
**Phase:** 1 — Control Plane Foundation  
**Python target:** 3.12  
**Database:** PostgreSQL 16  
**Coordination:** Redis 7  
**Framework:** FastAPI, SQLAlchemy 2, Alembic, pydantic-settings

## Included

- Secure project and administrator authentication
- Project, model-alias, API-key, worker-enrollment, and revocation administration
- Durable PostgreSQL request queue with `SKIP LOCKED`
- Idempotency constraint and single-result commitment
- Transactional budget reservation and reconciliation
- Worker heartbeat, pull, result, error, renewal, and stale-worker maintenance
- Redis burst limiting and circuit-breaker service
- Safe structured errors, secret redaction, body-size limits, and request IDs
- Docker Compose, Alembic migration, CI, security scans, tests, and open-source governance

## Explicitly deferred

- ORBI Console/dashboard
- Colab and Kaggle notebooks
- Local model runtime and Docker inference node
- Hugging Face managed fallback
- SSE token streaming
- Async `/v1/jobs` and webhooks
- Python and TypeScript SDKs
- n8n reporting workflows
- Prometheus/Grafana deployment
- Kubernetes, Helm, and Terraform

## Files created

1. `.env.example`
2. `.github/CODEOWNERS`
3. `.github/ISSUE_TEMPLATE/bug_report.yml`
4. `.github/ISSUE_TEMPLATE/config.yml`
5. `.github/ISSUE_TEMPLATE/feature_request.yml`
6. `.github/PULL_REQUEST_TEMPLATE.md`
7. `.github/dependabot.yml`
8. `.github/workflows/security.yml`
9. `.github/workflows/test.yml`
10. `.gitignore`
11. `CHANGELOG.md`
12. `CODE_OF_CONDUCT.md`
13. `CONTRIBUTING.md`
14. `GOVERNANCE.md`
15. `LICENSE`
16. `README.md`
17. `ROADMAP.md`
18. `SECURITY.md`
19. `apps/gateway/Dockerfile`
20. `apps/gateway/alembic.ini`
21. `apps/gateway/alembic/env.py`
22. `apps/gateway/alembic/script.py.mako`
23. `apps/gateway/alembic/versions/0001_phase1_foundation.py`
24. `apps/gateway/entrypoint.sh`
25. `apps/gateway/src/orbi_gateway/__init__.py`
26. `apps/gateway/src/orbi_gateway/config.py`
27. `apps/gateway/src/orbi_gateway/database.py`
28. `apps/gateway/src/orbi_gateway/dependencies.py`
29. `apps/gateway/src/orbi_gateway/errors.py`
30. `apps/gateway/src/orbi_gateway/logging.py`
31. `apps/gateway/src/orbi_gateway/main.py`
32. `apps/gateway/src/orbi_gateway/middleware.py`
33. `apps/gateway/src/orbi_gateway/models/__init__.py`
34. `apps/gateway/src/orbi_gateway/models/base.py`
35. `apps/gateway/src/orbi_gateway/models/entities.py`
36. `apps/gateway/src/orbi_gateway/routes/__init__.py`
37. `apps/gateway/src/orbi_gateway/routes/admin.py`
38. `apps/gateway/src/orbi_gateway/routes/chat.py`
39. `apps/gateway/src/orbi_gateway/routes/health.py`
40. `apps/gateway/src/orbi_gateway/routes/internal/__init__.py`
41. `apps/gateway/src/orbi_gateway/routes/internal/workers.py`
42. `apps/gateway/src/orbi_gateway/routes/models.py`
43. `apps/gateway/src/orbi_gateway/routes/usage.py`
44. `apps/gateway/src/orbi_gateway/schemas/__init__.py`
45. `apps/gateway/src/orbi_gateway/schemas/api.py`
46. `apps/gateway/src/orbi_gateway/services/__init__.py`
47. `apps/gateway/src/orbi_gateway/services/api_keys.py`
48. `apps/gateway/src/orbi_gateway/services/budget.py`
49. `apps/gateway/src/orbi_gateway/services/circuit_breaker.py`
50. `apps/gateway/src/orbi_gateway/services/idempotency.py`
51. `apps/gateway/src/orbi_gateway/services/queue.py`
52. `apps/gateway/src/orbi_gateway/services/rate_limit.py`
53. `apps/gateway/src/orbi_gateway/services/worker_health.py`
54. `apps/gateway/src/orbi_gateway/services/worker_tokens.py`
55. `apps/gateway/tests/integration/test_phase1_lifecycle.py`
56. `apps/gateway/tests/security/test_auth_boundaries.py`
57. `apps/gateway/tests/security/test_error_redaction.py`
58. `apps/gateway/tests/security/test_security_middleware.py`
59. `apps/gateway/tests/security/test_worker_scope_boundary.py`
60. `apps/gateway/tests/unit/test_api_keys.py`
61. `apps/gateway/tests/unit/test_budget.py`
62. `apps/gateway/tests/unit/test_circuit_breaker.py`
63. `apps/gateway/tests/unit/test_idempotency.py`
64. `apps/gateway/tests/unit/test_logging.py`
65. `apps/gateway/tests/unit/test_worker_tokens.py`
66. `deploy/docker-compose.yml`
67. `docs/api-reference.md`
68. `docs/phase-1-build-confirmation.md`
69. `docs/phase-1-decisions.md`
70. `docs/phase-1-verification.md`
71. `docs/rfcs/README.md`
72. `docs/security.md`
73. `pyproject.toml`
74. `scripts/bootstrap-dev.py`

**Total files:** 74
