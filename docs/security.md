# ORBI Phase 1 Security Model

## Credentials

ORBI project keys use this format:

```text
orbi_<live|test>_v1_<random-key-id>_<random-secret>
```

The random key ID is a non-secret database lookup identifier. ORBI stores only an Argon2id hash of
`secret + server-side pepper`. The full key is returned once and is never persisted.

Workers use one-time enrollment tokens over TLS. A consumed enrollment token creates a worker
record and a short-lived RS256 JWT. The worker's current JWT ID is stored in PostgreSQL, allowing
immediate revocation or rotation without relying on Redis availability.

## Correctness boundary

ORBI provides:

- At-least-once request delivery
- PostgreSQL-enforced idempotency
- Atomic single-result commitment
- Worker assignment checks on result and error submission
- Token-budget reservation under a project row lock
- Lease recovery for crashed workers

ORBI does **not** promise that failed inference compute can never run twice. Distributed failure can
consume compute on a worker whose result never reaches the control plane. ORBI guarantees that at
most one matching result is accepted and accounted as the committed response.

## Logging

Structured logs redact ORBI-shaped project, worker, and administrator credentials. Unexpected
exceptions log only their class name. Public errors never contain stack traces, database details,
or raw validation input.

## Trust boundaries

- PostgreSQL, Redis, signing keys, and peppers belong to the trusted control-plane zone.
- Workers receive only short-lived scoped JWTs and their assigned request payloads.
- Workers never receive database credentials, API-key hashes, project records, or unrelated jobs.
- External inference providers and notification systems remain separate third-party trust zones.
