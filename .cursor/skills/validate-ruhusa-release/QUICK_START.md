# Quick Start: Ruhusa v0.7.0 Validation

## Four validation lanes

| Lane | What it proves | Requires |
|---|---|---|
| in-memory | Authorization, provenance, execution, replay, recovery | Python + uv |
| postgres | Durable PostgreSQL stores and concurrency | Docker or external PG 17 |
| resilience | Real outage/recovery, container restart durability | Docker |
| tamper | Audit hash-chain tamper evidence | Docker (isolated DB) |

A full **PASS** requires all four lanes to run with zero failures, errors, or skips.

---

## Lane 1 — In-memory (fast, ~2s)

```bash
uv sync
mkdir -p .validation-results
uv run pytest tests/ -m "not postgres" --tb=short \
  --junitxml=".validation-results/in-memory.xml"
```

Expected: ≥ 38 tests, 0 failed, 0 skipped.

---

## Lane 2 — PostgreSQL (non-destructive)

```bash
docker compose up -d postgres
# wait ~5s for readiness
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@127.0.0.1:5432/ruhusa_demo"

uv run pytest tests/ -m "postgres and not destructive_postgres and not tamper" \
  --tb=short --junitxml=".validation-results/postgres.xml"
```

---

## Lane 3 — Resilience (isolated DB, destructive)

```bash
export COMPOSE_PROJECT_NAME="ruhusa_validation_resilience"
export RUHUSA_POSTGRES_PORT="55432"
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@127.0.0.1:55432/ruhusa_demo"
export RUHUSA_ALLOW_DESTRUCTIVE_TESTS="1"

docker compose up -d postgres
# wait for readiness

uv run pytest tests/test_postgres_resilience.py -m destructive_postgres \
  --tb=short --junitxml=".validation-results/resilience.xml"

docker compose down -v --remove-orphans
unset RUHUSA_ALLOW_DESTRUCTIVE_TESTS RUHUSA_POSTGRES_PORT COMPOSE_PROJECT_NAME
```

---

## Lane 4 — Tamper evidence (isolated DB, destructive)

```bash
export COMPOSE_PROJECT_NAME="ruhusa_validation_tamper"
export RUHUSA_POSTGRES_PORT="55433"
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@127.0.0.1:55433/ruhusa_demo"
export RUHUSA_ALLOW_DESTRUCTIVE_TESTS="1"

docker compose up -d postgres
# wait for readiness

uv run pytest tests/test_tamper.py -m tamper \
  --tb=short --junitxml=".validation-results/tamper.xml"

docker compose down -v --remove-orphans
unset RUHUSA_ALLOW_DESTRUCTIVE_TESTS RUHUSA_POSTGRES_PORT COMPOSE_PROJECT_NAME
```

---

## Generate the validation report

```bash
uv run python tests/report_generator.py \
  --junit-dir .validation-results \
  --output RUHUSA_V0_7_VALIDATION.md \
  --ruhusa-version "$(grep 'tag = ' pyproject.toml | head -1 | grep -o 'v[0-9.]*')" \
  --postgres-version "17"

cat RUHUSA_V0_7_VALIDATION.md
```

The report reads JUnit XML evidence only — it never re-runs tests and never hardcodes PASS.

---

## For future releases

1. Update `tag = "vX.Y.Z"` in `pyproject.toml`
2. Run `uv sync`
3. Run all four lanes above
4. Generate and review `RUHUSA_V0_7_VALIDATION.md`

See `SKILL.md` for detailed failure classification and security invariant reference.
