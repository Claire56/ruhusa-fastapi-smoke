# Ruhusa v0.7.0 External Validation Report

**Generated:** 2026-08-29T00:02:22.648263+00:00  
**Ruhusa target:** v0.7.0  
**Python running report generator:** 3.13.13  
**PostgreSQL target:** 17

## Verdict

# **FAIL**

A full **PASS** is emitted only when every mandatory validation lane produced
JUnit evidence and there were zero failures, errors, or skipped tests.

## Validation lanes

| Lane | Security property | Tests | Passed | Failed/Error | Skipped | Result |
|---|---|---:|---:|---:|---:|---|
| in-memory | Authorization, provenance, execution, replay, recovery | 40 | 40 | 0 | 0 | **PASS** |
| postgres | Durable PostgreSQL stores and concurrency | 0 | 0 | 0 | 0 | **NOT TESTED** |
| resilience | Real PostgreSQL outage/recovery and container restart | 0 | 0 | 0 | 0 | **NOT TESTED** |
| tamper | Audit hash-chain tamper evidence | 0 | 0 | 0 | 0 | **NOT TESTED** |

## Totals

| Metric | Count |
|---|---:|
| Tests | 40 |
| Passed | 40 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |

## What was NOT tested

- `postgres`: mandatory lane did not produce JUnit evidence
- `resilience`: mandatory lane did not produce JUnit evidence
- `tamper`: mandatory lane did not produce JUnit evidence

## Findings

- None

## Evidence files

- `in-memory-py3.13.xml`

## Validation contract

The suite is an external-consumer validation of the released Ruhusa package.
It does not modify Ruhusa and does not treat HTTP status alone as security
evidence. Protected side-effect invariants are asserted in authorization,
replay, concurrency, UNKNOWN, recovery, and database-outage tests.
