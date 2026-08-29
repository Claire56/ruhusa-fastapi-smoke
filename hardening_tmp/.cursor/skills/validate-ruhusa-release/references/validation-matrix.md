# Ruhusa release validation matrix

This matrix defines the mandatory external-consumer validation lanes for the
Ruhusa release pinned in `pyproject.toml`.

## 1. In-memory core security

Must verify:

- application imports and starts
- ALLOW for authorized small refund
- REQUIRE_APPROVAL for refund above policy threshold
- default DENY for unauthorized principal
- expired task denied
- expired canonical invocation denied
- principal/action/resource/arguments/task provenance mismatches denied
- tool ID, implementation ID, and allowed-action integrity
- AVAILABLE → CLAIMED → COMPLETED lifecycle
- execution-time authority revalidation
- completed invocation replay blocked
- no additional protected side effect on replay
- stale claim → UNKNOWN
- UNKNOWN automatic retry blocked
- reconciliation while CLAIMED rejected
- SIDE_EFFECT_NOT_APPLIED → AVAILABLE → same invocation attempt 2 → COMPLETED
- SIDE_EFFECT_CONFIRMED → COMPLETED → retry blocked
- recovery does not bypass current authorization
- stale attempt-1 permit cannot complete attempt 2
- audit failure turns otherwise-ALLOW into fail-closed DENY

## 2. Non-destructive PostgreSQL integration

Must use real PostgreSQL 17.

Verify:

- execution state persists through a fresh connection pool/store
- invocation provenance persists through a fresh pool/store
- tool registration persists through a fresh pool/store
- audit events persist through a fresh PostgresAuditLog
- hash chain verifies from a fresh audit instance
- same-invocation UNKNOWN recovery reaches attempt 2
- 20-way same-invocation race has exactly one winner
- concurrency race is repeated at least 25 rounds
- concurrent audit writers produce one valid serialized chain
- concurrent reconciliation has exactly one successful recovery

## 3. PostgreSQL resilience

Must run in a dedicated isolated Docker Compose job.

Verify:

- record protected side-effect count
- stop PostgreSQL while FastAPI process remains alive
- otherwise-valid protected request fails
- protected side-effect count does not increase
- restart PostgreSQL
- same FastAPI process/pool recovers
- new valid operation succeeds
- create durable execution/audit state
- restart actual PostgreSQL container
- durable execution record survives
- audit event survives
- audit chain still verifies

## 4. Tamper evidence

Must run in a separate disposable PostgreSQL job after all other validation for
that database.

Verify:

- create multiple real audit events
- `verify_chain()` is true before mutation
- directly mutate a historical persisted audit field
- `verify_chain()` becomes false

This demonstrates tamper evidence, not privileged-database immutability.

## Result rules

Allowed report outcomes:

- PASS
- PASS WITH FINDINGS
- FAIL

A mandatory lane with no JUnit evidence is FAIL.

Any test failure or error is FAIL.

Any skipped mandatory test prevents full PASS.

Full PASS requires all four lanes to run successfully with zero skips.
