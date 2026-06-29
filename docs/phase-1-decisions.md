# Phase 1 Architecture Corrections

The uploaded v1.0 implementation prompt was treated as a requirements draft, not executable truth.
Phase 1 applies these corrections:

1. **Argon2id is authoritative.** API keys use `orbi_<env>_v1_<key_id>_<secret>`. The random
   `key_id` is a non-secret lookup identifier; only an Argon2id hash of `secret + pepper` is stored.
2. **The first eight characters are not a usable lookup prefix.** They are shared by every key in
   the same environment and would force broad candidate scans.
3. **Idempotency is database-enforced.** A unique `(api_key_id, idempotency_key)` constraint is the
   correctness boundary. Redis is only an optional acceleration layer.
4. **Exactly-once execution is not promised.** ORBI uses at-least-once delivery and atomically
   commits at most one accepted result. A failed worker may have consumed compute before failover.
5. **OpenAI compatibility is semantic, not cosmetic.** `/v1/chat/completions` waits for completion
   up to a configured timeout. Async acceptance belongs to `/v1/jobs`, which is deferred.
6. **Worker enrollment avoids a shared notebook PSK.** Phase 1 uses one-time enrollment tokens over
   TLS, exchanged for short-lived scoped JWTs. Ed25519 proof-of-possession is a later hardening item.
7. **JWT keys are mounted files.** Multiline private keys are not placed directly in environment
   variables or committed Compose files.
8. **PostgreSQL 16 and Redis 7 run locally through Docker Compose.** Supabase/Upstash are compatible
   deployment options, not mandatory for local development.
9. **NATS JetStream is not described as end-to-end exactly-once.** Any later queue migration must
   retain application-level idempotency and result commitment.
10. **Queue capability requirements are explicit.** `orbi_requests.required_capabilities` exists
    and is checked during worker claims.
