# Ruhusa v0.7.0 External Validation Matrix

Use this repository (`ruhusa-fastapi-smoke`) as an **external consumer application** to independently verify that Ruhusa v0.7.0's important security, persistence, execution, failure, and recovery guarantees work.

## Ground Rules

- Do **not** modify the Ruhusa repository.
- Do **not** copy Ruhusa implementation code into this app.
- Test Ruhusa through its public APIs.
- Keep the app pinned to **Ruhusa v0.7.0**.
- FastAPI must remain an external integration, not a Ruhusa dependency.
- Use the existing PostgreSQL 17 Docker container for persistence tests.
- Tests involving PostgreSQL must use a real PostgreSQL instance, not mocks.
- Test helpers may be added to the smoke app where necessary.
- Do not weaken security behavior just to make a test pass.
- Do not automatically retry `UNKNOWN` executions.
- Every protected side-effect test must assert the number of actual side effects, not just HTTP status.
- Tests must clean up after themselves or use unique UUID-based invocation/task/account IDs.

### PostgreSQL Setup for First Run

See `../POSTGRES_SETUP.md` for complete instructions. Quick version:

```bash
docker compose up -d postgres
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
uv run pytest tests/ -v
```

---

## Test Categories

### 1. Basic Installation and Application Tests

Verify:

- Ruhusa reports version `0.7.0`.
- FastAPI application imports successfully.
- Application starts successfully.
- `GET /health` works.
- In-memory mode works without PostgreSQL.
- PostgreSQL mode works when `RUHUSA_POSTGRES_DSN` is configured.
- PostgreSQL-specific classes are imported from `ruhusa.postgres`, not the base package.
- The application does not import Ruhusa private/internal modules.

**Expected result:** All basic startup tests pass.

### 2. Authorization Tests

Test independently:

#### ALLOW
```
account_id: "authorization-test"
amount: 100
principal_id: "billing-agent"
```
**Expected:** effect = allow, executed = true, state = completed

#### REQUIRE_APPROVAL
Request amount greater than 500.
**Expected:** effect = require_approval, executed = false, no side effect

#### Default DENY
Use: principal_id = "rogue-agent"
**Expected:** effect = deny, executed = false

#### Expired task
Create an otherwise valid invocation whose task has expired.
**Expected:** DENY, no permit, no side effect

#### Invalid/expired invocation
Test an expired canonical invocation.
**Expected:** DENY, no execution permit

### 3. Invocation Integrity / Provenance Tests

Create valid canonical invocation records, then deliberately change one field:

- principal mismatch
- action mismatch
- resource mismatch
- arguments mismatch / arguments digest mismatch
- task ID mismatch
- unknown invocation ID
- untrusted tool ID
- incorrect implementation ID
- tool not authorized for requested action

**For every case:** authorization/execution must fail, no execution permit, no side effect.

### 4. Normal Execution Lifecycle

Verify a successful action transitions:
```
AVAILABLE → CLAIMED → revalidation → side effect → COMPLETED
```

**Assert:**
- attempt_count = 1
- claim_id exists
- completed_at exists
- exactly one side effect
- execution-time revalidation occurs before the protected side effect

### 5. Replay Protection

Create and successfully complete one invocation.

Attempt the **exact same invocation again**.

**Expected:**
- authorization may still = allow
- execution_allowed = false
- permit_issued = false
- reason indicates execution already completed
- state_before = completed, state_after = completed
- attempt_count_before = 1, attempt_count_after = 1
- exactly one side effect total

### 6. Concurrent Single-Winner Execution

Use one fresh canonical invocation.

Launch **20 concurrent HTTP callers** attempting the exact same execution.

**Expected:**
- 20 callers, 1 winner, 19 blocked
- 1 execution permit, 1 claim_id
- attempt_count = 1, state = completed
- exactly 1 side effect

Repeat this test multiple times (at least 25 rounds).

Every round must produce exactly one winner.

### 7. Audit Logging

Verify authorization decisions create audit events.

Test: DENY, ALLOW, ALLOW execution-time revalidation, REQUIRE_APPROVAL

**Verify:**
- audit count increases appropriately
- previous_hash links to prior event_hash
- verify_chain() = true

Restart FastAPI and confirm:
- audit events still exist
- verify_chain() remains true

### 8. Audit Failure / Fail-Closed Test

Use a deliberately failing `AuditLog` implementation in a test fixture.

Create an operation where policy would normally return: ALLOW

Force audit append to raise an exception.

**Expected final result:**
- DENY
- reason indicates audit unavailable/default deny
- no execution permit
- no side effect

**This is a mandatory security invariant:** ALLOW + audit failure must never escape as ALLOW.

### 9. PostgreSQL Execution Durability

Execute an allowed refund with PostgreSQL.

Record: invocation_id, claim_id, attempt_count, state

Restart the FastAPI process.

Retrieve the execution again.

**Expected:** Same invocation_id, claim_id, state = completed, attempt_count = 1. No state may disappear after process restart.

### 10. PostgreSQL Audit Durability

Create several audit events.

Restart FastAPI.

**Expected:** Same events remain, event count remains correct, verify_chain() = true.

### 11. Abandoned Execution / Stale Claim

Create an invocation and call `begin()` so it becomes: CLAIMED

Do **not** perform the side effect and do not call `complete()`.

**Before the stale threshold:** mark stale should NOT change state

**After the stale threshold:**
- CLAIMED → UNKNOWN
- state = unknown
- attempt_count = 1
- claim_id preserved

### 12. UNKNOWN Must Block Automatic Retry

Attempt to execute the same invocation while state is: UNKNOWN

**Expected:**
- authorization may still = allow
- execution_allowed = false
- permit_issued = false
- state remains unknown
- attempt_count remains 1
- no side effect

**This test is mandatory.** UNKNOWN must never automatically become AVAILABLE.

### 13. Invalid Reconciliation While CLAIMED

Try to reconcile an execution while it is still: CLAIMED

**Expected:**
- reconciled = false
- state remains claimed
- recovery_count = 0

Only UNKNOWN executions may be reconciled.

### 14. Recovery: SIDE_EFFECT_NOT_APPLIED

Create: CLAIMED → stale → UNKNOWN

Then trusted reconciliation states: SIDE_EFFECT_NOT_APPLIED

**Expected:**
- UNKNOWN → AVAILABLE
- reconciled = true
- recovery_count = 1
- attempt_count = 1

Then immediately retry while task/invocation are still valid.

**Expected:**
- new permit issued
- attempt = 2, attempt_count = 2
- side effect executes once
- state = completed

Overall: Attempt 1 (CLAIMED → UNKNOWN → AVAILABLE) → Attempt 2 (COMPLETED)

### 15. Recovery: SIDE_EFFECT_CONFIRMED

Create: CLAIMED → UNKNOWN

Trusted reconciliation reports: SIDE_EFFECT_CONFIRMED

**Expected:**
- UNKNOWN → COMPLETED
- reconciled = true
- recovery_count = 1

Attempt execution again.

**Expected:** blocked, no permit, no additional side effect.

### 16. Recovery Must Not Bypass Authorization

Create an UNKNOWN execution.

Reconcile: SIDE_EFFECT_NOT_APPLIED (state → AVAILABLE)

Allow its task to expire.

Attempt execution.

**Expected:**
- DENY because task expired
- no permit
- state remains available
- attempt_count unchanged

Recovery does not grant authorization by itself.

### 17. Permit Fencing / Stale Permit Test

Obtain permit for attempt 1.

Move execution: CLAIMED → UNKNOWN → SIDE_EFFECT_NOT_APPLIED → AVAILABLE

Obtain a new permit for attempt 2.

Attempt to use the **old attempt-1 permit** to call operations such as completion/release.

**Expected:**
- old permit rejected
- only the permit containing the current invocation_id, claim_id, attempt may mutate
- old permit must never complete attempt 2

### 18. PostgreSQL Outage / Fail-Closed Test

Keep FastAPI running.

Record current side-effect count.

Stop PostgreSQL: `docker compose stop postgres`

Verify health fails.

Attempt an otherwise-valid $100 refund.

**Expected:**
- request fails (HTTP 500 or preferably 503)
- NO side effect
- side-effect count unchanged

**Critical assertion:** security-state database unavailable → protected action does not execute.

### 19. PostgreSQL Recovery

Without restarting FastAPI, start PostgreSQL again: `docker compose start postgres`

Wait until healthy.

**Expected:**
- GET /health → healthy
- audit chain valid

Submit a new valid refund.

**Expected:** ALLOW, executed = true, state = completed.

This proves the application recovers after infrastructure restoration.

### 20. PostgreSQL Restart Durability

Restart the PostgreSQL container itself (do not clear volumes).

Verify previously stored items still exist and behave correctly:
- audit events
- execution records
- invocation records
- tool registrations

### 21. Concurrent Reconciliation

Create one execution in: UNKNOWN

Launch multiple callers simultaneously attempting the same trusted reconciliation.

**Expected:**
- exactly one reconciliation succeeds
- recovery_count = 1
- final state deterministic
- no double recovery

### 22. Audit Concurrency

Generate many authorization requests concurrently.

**Expected:**
- all expected audit events exist
- one serialized hash chain
- verify_chain() = true
- no duplicate sequence positions
- no broken previous_hash links

Use PostgreSQL for this test.

### 23. Tamper Detection

Use an isolated test database.

Create several PostgreSQL audit events.

Confirm: verify_chain() = true

Deliberately modify one stored historical audit value directly in PostgreSQL.

Then: verify_chain() must = false

Do not run this against shared development data. Reset the isolated database afterward.

This validates **tamper evidence**, not tamper-proof storage.

### 24. Side-Effect Invariants

Across every security/failure test, maintain an explicit side-effect counter.

Tests must assert:
- DENY → 0 effects
- REQUIRE_APPROVAL → 0 effects
- replay → 0 additional effects
- 19 concurrency losers → 0 effects
- UNKNOWN retry → 0 effects
- expired task → 0 effects
- DB outage → 0 effects
- provenance mismatch → 0 effects

Do not consider a test passed merely because an HTTP response looks correct.

### 25. Automated Test Organization

Organize pytest tests approximately as:

```
tests/
    test_authorization.py
    test_provenance.py
    test_execution.py
    test_replay.py
    test_concurrency.py
    test_audit.py
    test_durability.py
    test_failure_recovery.py
    test_database_outage.py
```

PostgreSQL tests marked with: `@pytest.mark.postgres`

Run:
- Normal tests: `uv run pytest`
- Real PostgreSQL integration tests: `uv run pytest -m postgres`

### 26. Final Validation Report

Create: `RUHUSA_V0_7_VALIDATION.md`

Include a table with:

| Test | Security property | Backend used | Result | Evidence |
|------|-------------------|--------------|--------|----------|

Use: PASS, FAIL, NOT TESTED

Do not mark something PASS unless the automated test actually ran.

At the bottom report:
- Total tests
- Passed
- Failed
- Skipped
- PostgreSQL tests passed
- Ruhusa version tested
- Python version
- FastAPI version
- PostgreSQL version

Identify findings as:
- Ruhusa bug
- Smoke-app integration issue
- Documentation/usability issue
- Upstream dependency warning

Do not modify Ruhusa to fix anything. Report potential Ruhusa issues first.

---

## Definition of Success

The smoke application should provide independent evidence for:

```
Request
   ↓
Canonical invocation/provenance
   ↓
Authorization
   ↓
Audit
   ↓
Atomic execution claim
   ↓
Execution-time revalidation
   ↓
Protected side effect
   ↓
Completion
```

And under failure:

```
untrusted / invalid / unavailable / uncertain
                  ↓
               BLOCK
```

with recovery only through an explicit trusted reconciliation process.
