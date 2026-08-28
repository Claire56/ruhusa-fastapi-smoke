# Ruhusa FastAPI Smoke App

A small external FastAPI service that consumes the stable `Ruhusa v0.7.0`
release exactly like an adopter would.

## Scenarios

- `billing-agent`, refund <= 500: `ALLOW` and execute
- `billing-agent`, refund > 500: `REQUIRE_APPROVAL`, no side effect
- any other principal: default `DENY`

An allowed request exercises canonical invocation registration, Ruhusa
authorization, execution claim, execution-time revalidation, a fake protected
side effect, completion, and hash-chained audit logging.

## Run in-memory

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs

Allowed:

```bash
curl -X POST http://127.0.0.1:8000/refunds \
  -H "content-type: application/json" \
  -d '{"account_id":"123","amount":100,"principal_id":"billing-agent"}'
```

Approval required:

```bash
curl -X POST http://127.0.0.1:8000/refunds \
  -H "content-type: application/json" \
  -d '{"account_id":"123","amount":900,"principal_id":"billing-agent"}'
```

Default deny:

```bash
curl -X POST http://127.0.0.1:8000/refunds \
  -H "content-type: application/json" \
  -d '{"account_id":"123","amount":100,"principal_id":"rogue-agent"}'
```

Audit:

```bash
curl http://127.0.0.1:8000/audit
```

Tests:

```bash
uv run pytest
```

## Run with PostgreSQL

```bash
docker compose up -d postgres
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
uv run uvicorn app.main:app --reload
```

Then `GET /health` should report `"ruhusa_backend": "postgres"`.

FastAPI remains outside Ruhusa itself; this project tests Ruhusa's public
integration boundary without adding a web-framework dependency to the core.
