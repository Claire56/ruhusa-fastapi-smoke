# Ruhusa v0.7.0 External Validation Report

**Generated:** 2026-08-28T13:59:27-0700

**Report type:** External consumer validation from `ruhusa-fastapi-smoke`

This report validates the **released Ruhusa framework**. Ruhusa was not modified. Tests were not weakened to produce a pass.

---

## Environment

| Component | Version | Notes |
|-----------|---------|--------|
| Ruhusa | **0.7.0** | Pinned as git tag `v0.7.0`; installed package metadata matches |
| Python | **3.13.9** | Satisfies Ruhusa `Requires-Python: >=3.12` |
| FastAPI | **0.141.1** | External integration only |
| PostgreSQL | **17.11** | `postgres:17` via Docker Compose; database `ruhusa_demo` |
| pytest | 8.4.2 | |

Intended version: **v0.7.0**. Installed version matches.

PostgreSQL classes are imported from `ruhusa.postgres`, not the base package.

---

## Test execution summary

### In-memory tests

```text
uv run pytest tests/ -v -m "not postgres"
43 passed, 8 deselected, 3 warnings in 0.51s
```

| Result | Count |
|--------|-------|
| Passed | 43 |
| Failed | 0 |
| Skipped | 0 |
| Exit code | 0 |
| **Status** | PASS |

### PostgreSQL tests

```text
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
uv run pytest tests/ -v -m postgres
5 passed, 3 skipped, 43 deselected, 3 warnings in 186.18s
```

| Result | Count |
|--------|-------|
| Configured | YES (`ruhusa_demo`) |
| Passed | 5 |
| Failed | 0 |
| Skipped | 3 |
| Exit code | 0 |
| **Status** | PASS, with skips |

Skipped PostgreSQL tests:

- `test_postgresql_unavailable_denies_execution` — requires stopping Postgres
- `test_postgres_container_restart_preserves_data` — requires restarting the container
- `test_tamper_detection_requires_isolated_database` — requires an isolated tamper database

### Totals

| Metric | Count |
|--------|-------|
| **Total passed** | 48 |
| **Total failed** | 0 |
| **Total skipped** | 3 |
| **PostgreSQL tests executed** | 8 collected (5 passed, 3 skipped) |

No security-invariant pytest failure occurred.

---

## Validation matrix

| Test | Security property | Backend | Result | Evidence |
|------|-------------------|---------|--------|----------|
| 1. Installation and application | Version, startup, health, public API, postgres import path | memory + postgres | PASS | `test_health`: `status=ok`, backend in `{memory, postgres}`, `audit_chain_valid=true`. Installed Ruhusa 0.7.0. `PostgresAuditLog` / `PostgresExecutionStore` live in `ruhusa.postgres`. |
| 2. Authorization ALLOW | billing-agent $100 executes | memory | PASS | `test_small_refund_allows_execution`: HTTP 200, `effect=allow`, `executed=true`, `execution_state=completed`. |
| 2. Authorization REQUIRE_APPROVAL | amount > 500 does not execute | memory | PASS | `test_large_refund_requires_approval`: HTTP 202, `effect=require_approval`, `executed=false`, refund count 0. |
| 2. Authorization default DENY | unknown principal cannot execute | memory | PASS | `test_unknown_principal_denied` (`rogue-agent`): HTTP 403, `effect=deny`, `executed=false`, refund count 0. |
| 2. Expired task / invocation | expiry is DENY, no side effect | memory | PASS | `test_expired_task_denied` and `test_expired_invocation_denied`: `allowed is False`; expired-task refund count 0. |
| 3. Provenance integrity | canonical invocation mismatch cannot execute | memory | PASS | Pytest denied principal, action, resource, arguments digest, unknown invocation, untrusted tool, wrong implementation, unauthorized action. Supplemental authorize(): mismatched `task_id` denied with `reason=invocation record is bound to a different task`. No pytest covers task-id mismatch. |
| 4. Execution lifecycle | AVAILABLE → CLAIMED → revalidate → COMPLETED; one side effect | memory | PASS | `test_execution_state_transitions_correctly`: `begin()` → `claimed`, `attempt_count=1`, `claim_id` set; revalidate allowed; `complete()` → `completed`. `test_single_side_effect_per_execution`: exactly one refund. `test_execution_time_revalidation_occurs`: revalidate with `$600` after `$100` claim returned `allowed=false`; no extra side effect. |
| 5. Replay protection | completed invocation cannot replay | memory | PASS | `test_replay_blocked_after_completion`: HTTP 409, `execution_allowed=false`, `permit_issued=false`, state stays `completed`, `attempt_count` stays 1, side-effect count unchanged. Replay may still have `authorization_effect=allow`. |
| 6. Concurrent single-winner | 20 callers, exactly one winner and one side effect | memory + postgres | PASS | In-memory: 20 callers, 1 winner, 19 blocked, 1 side effect. Postgres: 25 rounds of 20 callers, one winner and one side effect each (`test_postgres_concurrent_single_winner_25_rounds`). In-memory repeated race is only 3 rounds. |
| 7. Audit logging | decisions audited; hash chain valid | memory | PASS | ALLOW / REQUIRE_APPROVAL / DENY created events; `chain_valid=true`. FastAPI process restart was not performed. |
| 8. Audit fail-closed | ALLOW + audit failure must not escape as ALLOW | memory | PASS | `test_audit_failure_denies_operation`: policy would allow, `final_effect=deny`, `allowed=false`, side-effect count unchanged. |
| 9. PostgreSQL execution durability | completed execution survives process-equivalent restart | postgres | PASS | `test_execution_state_persists_after_restart`: fresh `PostgresExecutionStore` pool restored same `invocation_id`, `claim_id`, `state`, `attempt_count`. |
| 10. PostgreSQL audit durability | audit events survive FastAPI restart | postgres | NOT TESTED | `test_audit_events_persist_after_restart` re-GETs `/audit` on the same process. FastAPI was not restarted. |
| 11. Stale claim → UNKNOWN | abandoned CLAIMED becomes UNKNOWN; claim_id preserved | memory | PASS | `/failure/claim-only` then `/failure/stale/{id}` → `state=unknown`, `claim_id` present. |
| 12. UNKNOWN blocks automatic retry | UNKNOWN must not become AVAILABLE by retry | memory | PASS | `begin()` while UNKNOWN returned `allowed=false`; side-effect count unchanged. |
| 13. Invalid reconciliation while CLAIMED | only UNKNOWN may be reconciled | memory | PASS | `reconciled=false`, state remained `claimed`. `recovery_count` was not asserted. |
| 14. Recovery SIDE_EFFECT_NOT_APPLIED | UNKNOWN → AVAILABLE, then same invocation attempt 2 | memory | PASS | Same `invocation_id`: reconcile → `available`; `begin()` issued permit `attempt=2`; `complete()` → `completed`, `attempt_count=2`. Attempt 2 did not increment the HTTP refund side-effect counter (controller-level complete only). |
| 15. Recovery SIDE_EFFECT_CONFIRMED | UNKNOWN → COMPLETED; retry blocked; no extra side effect | memory | PASS | `state=completed`, `recovery_count=1`, later `begin()` denied, side-effect count unchanged. |
| 16. Recovery does not bypass authorization | recovered AVAILABLE + expired task is DENY | memory | PASS | `begin()` denied after recovery; no side effect. |
| 17. Permit fencing | stale attempt-1 permit cannot complete attempt 2 | memory | PASS | `test_stale_permit_rejected`: `complete(permit1)` returned `False`; attempt 2 stayed `claimed` with `attempt_count=2`; `complete(permit2)` succeeded → `completed`. |
| 18. PostgreSQL outage fail-closed | DB unavailable ⇒ no protected side effect | postgres | NOT TESTED | `test_postgresql_unavailable_denies_execution` skipped (`Postgres stop/start coordination requires isolated test environment`). Postgres was not stopped. |
| 19. PostgreSQL recovery | restore DB without restarting the app; new ALLOW executes | postgres | NOT TESTED | No executed test starts Postgres again on the same FastAPI process and submits a new refund. |
| 20. PostgreSQL container restart | audit, execution, invocation, tools survive container restart | postgres | NOT TESTED | `test_postgres_container_restart_preserves_data` skipped. `test_tool_registration_persists` only checked in-process `is_trusted`. |
| 21. Concurrent reconciliation | exactly one reconciliation winner | memory | PASS | 5 concurrent callers, exactly one `reconciled=true`, `recovery_count=1`. |
| 22. Audit concurrency | concurrent writers keep one valid hash chain | postgres | PASS | 10 concurrent refunds all succeeded; `count >= 10`; `chain_valid=true`. |
| 23. Tamper detection | `verify_chain()` false after isolated DB mutation | postgres | NOT TESTED | Skipped. Destructive tamper was not run against `ruhusa_demo`. |
| 24. Side-effect invariants | DENY / approval / replay / losers / UNKNOWN / expiry / provenance produce 0 extra effects | memory + postgres | PASS | Asserted in authorization, replay, concurrency, UNKNOWN retry, confirmed recovery, and audit-failure tests. **Not** asserted for live PostgreSQL outage (see 18). |

Allowed results: **PASS**, **FAIL**, **NOT TESTED**. PASS is used only where a check actually ran.

---

## Release validation verdict

### PASS WITH FINDINGS

No tested security invariant failed. Ruhusa v0.7.0, consumed from this external FastAPI app, held default-deny, fail-closed audit, replay protection, UNKNOWN blocking, same-invocation recovery to attempt 2, stale-permit fencing, single-winner concurrency (including 25 PostgreSQL rounds), and execution durability across a fresh pool.

The verdict is not **PASS** because matrix-mandatory PostgreSQL outage, container-restart, FastAPI-restart audit durability, and tamper-detection checks were skipped or not executed.

The verdict is not **FAIL**: there was no demonstrated security-invariant failure.

### Security failures

None observed in executed tests.

No Ruhusa security behavior was changed to make a test pass.

---

## Findings

### Smoke-app integration issues

1. **PostgreSQL outage, recovery, and container restart are skipped.** Categories 18–20 were not exercised. Fail-closed behavior when the security-state database is down is unproven in this run.
2. **Tamper detection is skipped.** Category 23 needs an isolated database, which was not created.
3. **Audit durability does not restart FastAPI.** Category 10 re-reads `/audit` in the same process.
4. **No pytest for task-id mismatch.** Supplemental `authorize()` denied it; the suite does not cover that case.
5. **SIDE_EFFECT_NOT_APPLIED attempt 2 does not apply the HTTP refund side effect.** Lifecycle completed at the controller; the refund counter was not incremented.
6. **In-memory concurrency repeats 3 rounds, not 25.** PostgreSQL covered the 25-round requirement.
7. **Revalidation test changes request arguments** (`$100` claim vs `$600` revalidate), so deny may be provenance or policy. It still showed revalidation can block.

### Documentation / usability issues

1. FastAPI `on_event("shutdown")` is deprecated (FastAPI 0.141.1 lifespan warning). Smoke-app issue.
2. Starlette `TestClient` warns that `httpx` is deprecated in favor of `httpx2`.

### Ruhusa bugs

None identified from executed tests.

### Upstream dependency issues

None identified. Python 3.13.9 is within Ruhusa’s `>=3.12` range.

### Environment / infrastructure

PostgreSQL 17.11 was already running and healthy. Tests used dedicated database `ruhusa_demo`. Tamper tests were not pointed at that shared demo database.

---

## What was tested

- In-memory security validation: 43 pytest tests
- PostgreSQL integration: 5 pytest tests, including 25 rounds of 20-caller single-winner execution and concurrent audit-chain integrity
- Supplemental in-memory check: task-id mismatch deny

## What was not tested

- Live PostgreSQL stop while FastAPI remains up
- PostgreSQL start again without restarting FastAPI
- PostgreSQL container restart with volume preserved
- Audit tamper detection on an isolated database
- FastAPI process restart for audit durability

---

## How to run

### In-memory tests only

```bash
uv run pytest tests/ -v -m "not postgres"
```

### Full pytest validation (requires PostgreSQL)

```bash
docker compose up -d postgres
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
uv run pytest tests/ -v
```

### Stop PostgreSQL when done

```bash
docker compose down
```

---

**Test date:** 2026-08-28 13:59:27 -0700

**Verdict:** PASS WITH FINDINGS

This report reflects actual test execution. Categories marked NOT TESTED did not run a real check of that security property.
