---
name: validate-ruhusa-release
description: Validate a released Ruhusa version from this external FastAPI consumer application. Use when testing Ruhusa authorization, provenance, replay protection, concurrency, PostgreSQL durability, audit integrity, fail-closed behavior, execution recovery, or release readiness.
disable-model-invocation: true
icon: shield
color: green
---

# Validate Ruhusa Release

Validate the installed Ruhusa release using this repository as an
independent external consumer.

This skill validates the released framework. It must not modify the
Ruhusa repository or weaken tests to make failures pass.

## Core rule

Treat every failing test as evidence.

Classify failures as one of:

- Ruhusa bug
- smoke-app integration issue
- documentation/usability issue
- upstream dependency issue
- environment/infrastructure issue

Do not modify Ruhusa automatically.

## Before testing

1. Determine the Ruhusa version installed by this project.
2. Confirm it matches the version intended for validation.
3. Confirm Python satisfies Ruhusa's supported version.
4. Run the basic in-memory suite.
5. Set up PostgreSQL before running PostgreSQL tests (see below).
6. Use a dedicated test database for destructive tests.

## When you need help

Some tests require manual infrastructure coordination that the skill cannot automate:

**PostgreSQL outage/recovery test**: If skipped due to isolation requirements, ask the user to:
```bash
docker compose stop postgres        # Stop PostgreSQL
uv run pytest tests/test_durability.py::TestPostgresOutageAndRecovery::test_postgresql_unavailable_denies_execution -v
docker compose start postgres       # Restart PostgreSQL
```

**PostgreSQL container restart test**: If skipped, ask the user to run the test in isolation:
```bash
uv run pytest tests/test_durability.py::TestPostgresRestartDurability::test_postgres_container_restart_preserves_data -v
```

**Tamper detection test**: If skipped, ask the user to:
1. Create an isolated test database:
```bash
docker exec ruhusa-fastapi-smoke-postgres-1 createdb ruhusa_test_tamper -U postgres
```
2. Point the test at that database
3. Run the tamper test
4. Clean up: `docker exec ruhusa-fastapi-smoke-postgres-1 dropdb ruhusa_test_tamper -U postgres`

**FastAPI process restart test (audit durability)**: If needed, ask the user to:
1. Let the test run to generate audit events
2. Kill and restart the FastAPI process
3. Verify the audit chain persists

## PostgreSQL Setup

Before running PostgreSQL tests, start the database:

```bash
# Start PostgreSQL 17 service
docker compose up -d postgres

# Verify it's ready
docker compose exec postgres pg_isready -U postgres

# Set the environment variable for tests
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
```

Then run tests with PostgreSQL:

```bash
# Run all tests (in-memory + PostgreSQL)
uv run pytest tests/ -v

# Or just PostgreSQL tests
uv run pytest tests/ -v -m postgres
```

To stop PostgreSQL after testing:

```bash
docker compose down
```

## Security invariants

The following must never be weakened:

- default deny
- fail closed
- no unaudited ALLOW
- canonical invocation integrity
- immutable tool identity
- no delegated authority expansion
- execution-time revalidation
- completed invocation cannot replay
- UNKNOWN cannot automatically retry
- only trusted reconciliation may recover UNKNOWN
- stale execution permits cannot mutate newer attempts
- exactly one execution winner under concurrency
- protected side effects must not occur when authorization or trusted
  security state is unavailable

## Validation workflow

Read:

`references/validation-matrix.md`

Run every applicable validation category in that matrix.

For PostgreSQL tests:

- use real PostgreSQL
- do not mock PostgreSQL stores
- verify persistence across application restart
- verify persistence across PostgreSQL restart
- verify concurrent database behavior

For concurrency:

- use at least 20 concurrent callers
- repeat the race multiple times
- require exactly one winner per invocation
- require exactly one protected side effect

For failure tests:

- verify the side-effect counter, not only HTTP status
- backend failure must not produce a protected side effect

For UNKNOWN recovery:

- test SIDE_EFFECT_NOT_APPLIED
- test SIDE_EFFECT_CONFIRMED
- test invalid reconciliation while CLAIMED
- test retry blocked while UNKNOWN
- test stale permit fencing
- test recovery does not bypass fresh authorization

For audit:

- validate hash-chain integrity
- validate concurrent writers
- validate persistence
- test tamper detection only against an isolated test database

## Do not

Do not:

- add FastAPI to Ruhusa
- modify the Ruhusa repository
- change Ruhusa security behavior
- bypass failed tests
- silently retry UNKNOWN operations
- replace PostgreSQL integration tests with mocks
- classify a test as PASS unless it actually ran
- run destructive tamper tests against non-test data

## Final report

Generate or update:

`RUHUSA_V0_7_VALIDATION.md`

Include:

| Test | Security property | Backend | Result | Evidence |
|------|-------------------|---------|--------|----------|

Allowed results:

- PASS
- FAIL
- NOT TESTED

Also report:

- Ruhusa version
- Python version
- FastAPI version
- PostgreSQL version
- total tests
- passed
- failed
- skipped
- PostgreSQL tests executed
- security failures
- integration findings
- documentation findings

At the end provide a release-validation verdict:

- PASS
- PASS WITH FINDINGS
- FAIL

A FAIL caused by a security invariant must be highlighted separately and
must not be automatically fixed.
