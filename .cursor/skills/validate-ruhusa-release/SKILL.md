---
name: validate-ruhusa-release
description: >
  Run the complete external validation harness for the Ruhusa version pinned in
  pyproject.toml. Use for release sign-off, PR review, or when any security
  invariant needs verification. Covers authorization, provenance, replay,
  concurrency, UNKNOWN recovery, PostgreSQL durability, real outage/restart
  resilience, and audit tamper evidence.
---

# Ruhusa Release Validation Skill

This skill runs the external consumer validation harness for Ruhusa.
You are acting as an external verifier. **Never modify Ruhusa itself.**
Every failing test is evidence — classify it, do not suppress it.

---

## Step 0 — Read context before doing anything else

```bash
cat pyproject.toml | grep -A3 "\[tool.uv.sources\]"
python3 --version
uv --version
docker --version 2>/dev/null || echo "Docker not available"
```

Record:
- Ruhusa version tag (from `pyproject.toml`)
- Python version
- Whether Docker is available

If Python < 3.12, stop and report: **ENVIRONMENT FAIL — Python 3.12+ required.**

---

## Step 1 — Install dependencies

```bash
uv sync
```

If this fails, check the git tag in `pyproject.toml` is reachable and that
the network is available. Report any failure as **ENVIRONMENT FAIL**.

---

## Step 2 — Run the in-memory test suite

```bash
mkdir -p .validation-results
uv run pytest tests/ \
  -m "not postgres" \
  --tb=short \
  --junitxml=".validation-results/in-memory.xml" \
  2>&1 | tee .validation-results/in-memory.log
```

### What to check

Open `.validation-results/in-memory.log`. Confirm:

| Check | Expected |
|---|---|
| Exit code | 0 |
| Failed tests | 0 |
| Skipped tests | 0 |
| Tests collected | ≥ 38 |

### What each test group covers

- `test_authorization.py` — default deny, ALLOW, REQUIRE_APPROVAL, DENY, expired task/invocation
- `test_provenance.py` — principal/action/resource/arguments/tool integrity
- `test_execution_lifecycle.py` — AVAILABLE→CLAIMED→COMPLETED, claim_id, single side effect, execution-time revalidation
- `test_execution_revalidation.py` — task expiry between begin() and revalidate_before_execution() → cancelled state
- `test_replay.py` — completed invocation replay blocked, stale permit fencing (attempt-1 permit rejected after attempt 2)
- `test_audit.py` — ALLOW/DENY/REQUIRE_APPROVAL each create audit event, chain valid, fail-closed on audit failure
- `test_concurrency.py` / `test_concurrency_advanced.py` — exactly one winner, no double execution, concurrent audit serialization
- `test_failure_recovery.py` — CLAIMED→UNKNOWN, UNKNOWN blocks retry, reconcile while CLAIMED rejected, SIDE_EFFECT_NOT_APPLIED→AVAILABLE, SIDE_EFFECT_CONFIRMED→COMPLETED, recovery doesn't bypass authorization
- `test_recovery_end_to_end.py` — full HTTP end-to-end: UNKNOWN→SIDE_EFFECT_NOT_APPLIED→attempt 2→COMPLETED, exactly 1 side effect

### If any in-memory test fails

1. Read the full traceback in the log.
2. Classify using the table in Step 6.
3. Do NOT modify Ruhusa. Do NOT delete or skip the test.
4. Record the failure in the final report under "Security failures" or "Integration findings".
5. Continue to Step 3 anyway (PostgreSQL evidence is still needed).

---

## Step 3 — Start PostgreSQL and run non-destructive PostgreSQL tests

### 3a — Start PostgreSQL

```bash
docker compose up -d postgres
```

Wait for readiness (up to 60 seconds):

```bash
for i in $(seq 1 60); do
  docker compose exec -T postgres pg_isready -U postgres -d ruhusa_demo \
    >/dev/null 2>&1 && echo "ready" && break
  sleep 1
done
```

If PostgreSQL does not become ready, set `RUHUSA_POSTGRES_DSN` to an existing
external PostgreSQL 17 instance and skip the `docker compose` steps.
If no PostgreSQL is available, skip to Step 5 (resilience/tamper require Docker).

### 3b — Run non-destructive PostgreSQL tests

```bash
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@127.0.0.1:5432/ruhusa_demo"

uv run pytest tests/ \
  -m "postgres and not destructive_postgres and not tamper" \
  --tb=short \
  --junitxml=".validation-results/postgres.xml" \
  2>&1 | tee .validation-results/postgres.log
```

### What to check

| Check | Expected |
|---|---|
| Exit code | 0 |
| Failed tests | 0 |
| Skipped tests | 0 |

### What each postgres test covers

- `test_durability.py::test_execution_invocation_audit_and_tool_state_survive_fresh_pool` — creates refund via running app, opens an independent `psycopg` pool/stores, verifies execution state, invocation record, audit event (by `audit_id`), and tool registration are all readable from a fresh connection. Proves PostgreSQL durability across independent processes.
- `test_durability.py::test_audit_history_survives_fresh_audit_instance` — verifies a fresh `PostgresAuditLog` reads the same event and `verify_chain()` returns True.
- `test_recovery_end_to_end.py::test_postgres_recovered_same_invocation_executes_exactly_once_on_attempt_two` — same end-to-end recovery test as in-memory lane but asserts `current_runtime.backend == "postgres"`.
- Any concurrency or advanced tests marked `postgres`.

### If a postgres test fails

1. Check whether `RUHUSA_POSTGRES_DSN` is set and reachable.
2. Check whether `ruhusa.postgres` is available: `uv run python -c "from ruhusa.postgres import PostgresExecutionStore; print('ok')"`.
3. If the store API changed (e.g. `create_postgres_pool` signature mismatch), classify as **Ruhusa bug — API regression**.
4. If data is not found after a fresh pool read, classify as **Ruhusa bug — durability failure**.
5. Record and continue.

---

## Step 4 — Resilience: real PostgreSQL outage and container restart

These tests require Docker and a writeable environment. They run with
`RUHUSA_ALLOW_DESTRUCTIVE_TESTS=1` against an **isolated** Docker Compose project
so they do not affect the Step 3 database.

```bash
export COMPOSE_PROJECT_NAME="ruhusa_validation_resilience"
export RUHUSA_POSTGRES_PORT="55432"
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@127.0.0.1:55432/ruhusa_demo"
export RUHUSA_ALLOW_DESTRUCTIVE_TESTS="1"

docker compose down -v --remove-orphans 2>/dev/null || true
docker compose up -d postgres

for i in $(seq 1 60); do
  docker compose exec -T postgres pg_isready -U postgres -d ruhusa_demo \
    >/dev/null 2>&1 && echo "ready" && break
  sleep 1
done

uv run pytest tests/test_postgres_resilience.py \
  -m destructive_postgres \
  --tb=short \
  --junitxml=".validation-results/resilience.xml" \
  2>&1 | tee .validation-results/resilience.log

docker compose down -v --remove-orphans
unset RUHUSA_ALLOW_DESTRUCTIVE_TESTS RUHUSA_POSTGRES_PORT COMPOSE_PROJECT_NAME
```

### What each resilience test covers

- `test_database_outage_blocks_protected_side_effect_and_pool_recovers` —
  records side-effect count, calls `docker compose stop postgres`, sends a
  valid refund request, asserts HTTP ≥ 500 **and** side-effect count unchanged,
  then calls `docker compose start postgres`, waits for recovery, and asserts a
  new valid request succeeds with `execution_state == "completed"`.
- `test_postgres_container_restart_preserves_execution_and_audit_state` —
  creates a refund to get `invocation_id` and `audit_id`, calls
  `docker compose restart postgres`, opens a **fresh** pool after restart, and
  asserts execution record, audit event, and `verify_chain()` all survive.

### Key invariant being verified

**PostgreSQL outage must produce zero protected side effects.**
If the side-effect count increases during an outage, that is a
**critical Ruhusa security bug — fail-closed violated**.

### If resilience tests fail

- Side effect happened during outage → **CRITICAL: fail-closed invariant violated**
- Pool did not recover after restart → may be a psycopg-pool version issue; classify as **dependency/infrastructure issue**
- State not found after restart → **Ruhusa bug — PostgreSQL restart durability failure**

---

## Step 5 — Tamper evidence

These tests intentionally corrupt audit data. They **must** run against a
**separate, disposable** Docker Compose project that is destroyed afterward.

```bash
export COMPOSE_PROJECT_NAME="ruhusa_validation_tamper"
export RUHUSA_POSTGRES_PORT="55433"
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@127.0.0.1:55433/ruhusa_demo"
export RUHUSA_ALLOW_DESTRUCTIVE_TESTS="1"

docker compose down -v --remove-orphans 2>/dev/null || true
docker compose up -d postgres

for i in $(seq 1 60); do
  docker compose exec -T postgres pg_isready -U postgres -d ruhusa_demo \
    >/dev/null 2>&1 && echo "ready" && break
  sleep 1
done

uv run pytest tests/test_tamper.py \
  -m tamper \
  --tb=short \
  --junitxml=".validation-results/tamper.xml" \
  2>&1 | tee .validation-results/tamper.log

docker compose down -v --remove-orphans
unset RUHUSA_ALLOW_DESTRUCTIVE_TESTS RUHUSA_POSTGRES_PORT COMPOSE_PROJECT_NAME
```

### What the tamper test covers

`test_historical_audit_mutation_breaks_chain_verification`:
1. Resets the audit table to a clean state.
2. Creates two authorized refunds (generates ≥ 4 audit events including revalidation).
3. Asserts `verify_chain()` returns `True`.
4. Directly mutates `ruhusa_audit_events.reason` for `sequence = 1`.
5. Asserts `verify_chain()` returns `False`.

This proves the audit hash chain detects tampering. If `verify_chain()` returns
`True` after mutation, that is a **critical Ruhusa security bug — tamper detection broken**.

### If the tamper test fails

- `verify_chain()` is True after mutation → **CRITICAL: audit tamper not detected**
- Schema error (`ruhusa_audit_events` not found) → check `initialize_postgres_schema` ran
- `runtime.pool` is None → app started in memory mode; ensure `RUHUSA_POSTGRES_DSN` is set before the app module is imported

---

## Step 6 — Classify failures

For every failure, apply exactly one label:

| Symptom | Classification |
|---|---|
| Ruhusa API changed (import error, missing method, wrong signature) | **Ruhusa bug — API regression** |
| Security invariant violated (fail-closed, tamper, replay, duplicate side effect) | **Ruhusa bug — security invariant violated** |
| Wrong state transition (UNKNOWN not set, permit not rejected, recovery allows retry) | **Ruhusa bug — state machine regression** |
| `audit_id` missing from decision or re-validation result | **Ruhusa bug — audit record missing** |
| Test uses wrong endpoint path, wrong request shape, or wrong assertion | **Smoke-app integration issue** |
| `RUHUSA_POSTGRES_DSN` not set or unreachable host | **Environment/infrastructure issue** |
| Docker not running, port conflict, volume permission | **Environment/infrastructure issue** |
| Missing psycopg or psycopg-pool version | **Dependency issue** |
| Framework behavior works but docs are wrong | **Documentation/usability issue** |

**Never reclassify a security failure as an integration issue to make the suite green.**

---

## Step 7 — Generate the validation report

```bash
uv run python tests/report_generator.py \
  --junit-dir .validation-results \
  --output RUHUSA_V0_7_VALIDATION.md \
  --ruhusa-version "$(grep 'tag = ' pyproject.toml | head -1 | grep -o 'v[0-9.]*')" \
  --postgres-version "17"

cat RUHUSA_V0_7_VALIDATION.md
```

The report generator reads only JUnit XML files. It never re-runs tests.
It never hardcodes PASS. It produces:

- **PASS** — all four mandatory lanes (in-memory, postgres, resilience, tamper) have JUnit evidence, zero failures/errors/skips
- **PASS WITH FINDINGS** — all lanes ran, zero failures/errors, but some tests were skipped
- **FAIL** — any lane is missing evidence, or any test failed or errored

A FAIL caused by a missing lane (e.g. Docker unavailable) is distinct from a FAIL
caused by a test failure. State which in the final report.

---

## Step 8 — Final report to the user

After generating `RUHUSA_V0_7_VALIDATION.md`, report to the user:

```
## Validation summary

Ruhusa version: <tag>
Python: <version>
PostgreSQL: 17

### Results

| Lane | Tests | Passed | Failed | Skipped | Result |
|---|---|---|---|---|---|
| in-memory | N | N | N | N | PASS/FAIL |
| postgres | N | N | N | N | PASS/FAIL/NOT TESTED |
| resilience | N | N | N | N | PASS/FAIL/NOT TESTED |
| tamper | N | N | N | N | PASS/FAIL/NOT TESTED |

### Verdict: PASS / PASS WITH FINDINGS / FAIL

### Files changed (if any)
<list only smoke-app files changed, never Ruhusa files>

### Suspected Ruhusa bugs
<list with classification from Step 6, or "None">

### Smoke-app integration issues
<list or "None">
```

---

## Security invariant reference

These invariants must never be weakened or suppressed:

| Invariant | Verified by |
|---|---|
| Default deny | `test_authorization.py::test_deny_unauthorized_principal` |
| Fail closed (no security state) | `test_audit.py::test_audit_failure_denies_operation` |
| No unaudited ALLOW | all audit tests: every decision creates an audit event |
| Provenance integrity | `test_provenance.py` (8 tests) |
| Tool identity immutable | `test_provenance.py::test_untrusted_tool_id_denied`, `test_incorrect_implementation_id_denied` |
| Execution-time revalidation | `test_execution_revalidation.py`, `test_execution_lifecycle.py::test_execution_time_revalidation_occurs` |
| Completed replay blocked | `test_replay.py::test_replay_blocked_after_completion` |
| Stale permit fencing | `test_replay.py::TestPermitFencing::test_stale_permit_rejected` |
| UNKNOWN blocks automatic retry | `test_failure_recovery.py::TestUnknownBlocksAutomaticRetry` |
| Trusted reconciliation only | `test_failure_recovery.py::TestInvalidReconciliationWhileClaimed` |
| SIDE_EFFECT_NOT_APPLIED → attempt 2 | `test_recovery_end_to_end.py::test_recovered_same_invocation_executes_exactly_once_on_attempt_two` |
| SIDE_EFFECT_CONFIRMED → completed | `test_failure_recovery.py::TestRecoverySideEffectConfirmed` |
| Exactly one winner | `test_concurrency.py`, `test_concurrency_advanced.py` |
| Fail closed on DB outage | `test_postgres_resilience.py::test_database_outage_blocks_protected_side_effect_and_pool_recovers` |
| Audit tamper detectable | `test_tamper.py::test_historical_audit_mutation_breaks_chain_verification` |
| Durable across fresh pool | `test_durability.py` |

---

## What never to do

- Do not modify any file in the `ruhusa` package
- Do not mock PostgreSQL for PostgreSQL durability tests
- Do not change a failing assertion to make it pass
- Do not call `pytest.skip()` on a mandatory test
- Do not generate RUHUSA_V0_7_VALIDATION.md by hand or with hardcoded values
- Do not run tamper tests against non-disposable PostgreSQL data
- Do not classify a security invariant failure as a documentation issue
