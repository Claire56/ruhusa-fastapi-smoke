---
name: validate-ruhusa-release
description: Run the external Ruhusa release validation harness, including authorization, provenance, replay, concurrency, PostgreSQL durability, outage/recovery, UNKNOWN recovery, permit fencing, and audit tamper evidence.
disable-model-invocation: true
---

# Validate Ruhusa Release

Use this skill to validate the Ruhusa version pinned by this external FastAPI
consumer repository.

## Principle

Treat failures as evidence. Never modify Ruhusa merely to make the harness
green.

A result may be classified as:

- Ruhusa bug
- smoke-app integration issue
- documentation/usability issue
- dependency/environment issue

## Mandatory invariants

The harness must preserve and verify:

- default deny
- fail closed when trusted security state is unavailable
- no unaudited ALLOW
- canonical invocation/provenance integrity
- immutable tool implementation identity
- execution-time revalidation
- completed invocation replay protection
- single-winner concurrency
- UNKNOWN blocks automatic retry
- trusted reconciliation only
- SIDE_EFFECT_NOT_APPLIED requires a fresh authorization and new attempt
- SIDE_EFFECT_CONFIRMED permanently consumes execution authority
- stale permits cannot mutate newer attempts
- PostgreSQL state survives fresh processes/connections and container restart
- PostgreSQL outage produces no protected side effect
- audit-chain tampering is detectable

## How to run

Read `references/validation-matrix.md`.

Preferred command:

`bash .cursor/skills/validate-ruhusa-release/scripts/run-validation.sh`

The script uses an isolated Docker Compose PostgreSQL project, runs the
non-destructive and destructive lanes, runs tamper validation last, and creates
`RUHUSA_V0_7_VALIDATION.md` from JUnit evidence.

## Evidence rules

- HTTP status alone is insufficient for a security PASS.
- Protected side-effect counts must be asserted where applicable.
- A skipped mandatory test is not PASS.
- A missing mandatory JUnit lane is FAIL.
- Full PASS requires every mandatory lane to run with zero failure, error, or
  skipped tests.
- Tamper tests must run only against disposable isolated PostgreSQL data.

## Do not

Do not:

- add FastAPI to Ruhusa
- modify Ruhusa from this skill
- mock PostgreSQL for PostgreSQL guarantees
- automatically retry UNKNOWN executions
- weaken or delete a failing security assertion
- run tamper tests against shared development or production data
- infer PASS from a prior manual run

## Final output

The authoritative report is:

`RUHUSA_V0_7_VALIDATION.md`

The report must be generated from JUnit XML evidence by
`tests/report_generator.py`.
