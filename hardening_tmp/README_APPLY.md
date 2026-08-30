# Apply this hardening bundle to PR #1

This bundle is designed for the current
`cursor-validate-ruhusa-skill` branch of `ruhusa-fastapi-smoke`.

It does not modify Ruhusa itself.

## Replace these files

- `pyproject.toml`
- `docker-compose.yml`
- `tests/conftest.py`
- `tests/test_durability.py`
- `tests/test_tamper.py`
- `tests/report_generator.py`
- `.github/workflows/validation.yml`
- `.cursor/skills/validate-ruhusa-release/SKILL.md`
- `.cursor/skills/validate-ruhusa-release/references/validation-matrix.md`
- `.cursor/skills/validate-ruhusa-release/scripts/run-validation.sh`

## Add these files

- `tests/test_execution_revalidation.py`
- `tests/test_recovery_end_to_end.py`
- `tests/postgres_control.py`
- `tests/test_postgres_resilience.py`

The existing Cursor tests for authorization, provenance, replay, concurrency,
audit, and permit fencing can remain.

## Remove obsolete report generator if it still exists

Delete:

`tests/generate_report.py`

There must be only one authoritative report generator:
`tests/report_generator.py`.

## Local validation

Run:

`chmod +x .cursor/skills/validate-ruhusa-release/scripts/run-validation.sh`

Then:

`bash .cursor/skills/validate-ruhusa-release/scripts/run-validation.sh`

The script uses a separate Docker Compose project and host port 55432 by
default, destroys only that isolated validation volume when complete, and
writes:

`RUHUSA_V0_7_VALIDATION.md`

A full PASS requires in-memory, PostgreSQL, resilience, and tamper lanes all to
produce JUnit evidence with zero failures/errors/skips.
