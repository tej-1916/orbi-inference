# ORBI Node

The Phase 2 Milestone 1 node is a single-flight worker that enrolls with a one-time credential,
keeps its scoped JWT only in memory, sends heartbeats, polls the gateway, and returns deterministic
mock completions. It never connects to PostgreSQL or Redis.

All settings use the `ORBI_NODE_` prefix. Copy the documented values from the repository
`.env.example`; obtain the enrollment ID and secret from a freshly created one-time worker
enrollment credential.

```bash
python -m orbi_node.main
```

The mock runtime does not execute prompt content and does not contact an external model.
