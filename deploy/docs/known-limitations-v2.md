# OpenRath v2.0.0 known limitations

These limitations are part of the `2.0.0` operational contract.

- The Agent Server `/v1` HTTP contract remains Beta. Stable error
  codes and persisted fields are promoted only after compatibility review.
- v1 JSONL Sessions import as non-resumable history. They do not contain a
  durable program counter or an effect outcome.
- Embedded mode trusts the local process. It is not a multi-tenant isolation
  boundary.
- A synchronous Python step cannot be preempted safely in-process. The durable
  server profile rejects synchronous timeout declarations; use an async or
  isolated executor.
- Redis improves wake, cancel, and stream latency but never stores final Run
  state. Its loss falls back to bounded PostgreSQL polling.
- Exactly-once behavior is not promised for arbitrary external side effects.
  Non-idempotent ambiguous outcomes stop in `NEEDS_REVIEW`.
- The static-token reference application is a deployment example. Operators
  must integrate their identity provider, secret manager, TLS ingress, audit
  collector, retention, and network policy.
- OpenViking and live provider support remains conditional on the published
  compatibility range and successful lifecycle validation with the selected
  service.
- Capacity numbers are hardware/workload profiles, not universal SLA values.
- Webhooks, cron triggers, enterprise UI, SAML/SCIM, billing, and cross-region
  active-active storage are outside the v2.0.0 scope.
