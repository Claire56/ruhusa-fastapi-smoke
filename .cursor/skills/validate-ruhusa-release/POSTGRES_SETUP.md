# PostgreSQL Setup for Ruhusa Validation Tests

This guide explains how to set up PostgreSQL for running the complete validation suite.

## Quick Start

```bash
# 1. Start PostgreSQL
docker compose up -d postgres

# 2. Wait for it to be ready
docker compose exec postgres pg_isready -U postgres

# 3. Configure environment
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"

# 4. Run tests
uv run pytest tests/ -v

# 5. Stop when done
docker compose down
```

## Prerequisites

- **Docker** — PostgreSQL 17 runs in a container via `docker-compose.yml`
- **Docker Compose** — Included with Docker Desktop
- **Python 3.12+** — For running pytest

## Detailed Setup

### 1. Verify Docker is running

```bash
docker --version
docker compose version
```

If Docker isn't installed, install Docker Desktop from https://www.docker.com/products/docker-desktop

### 2. Start PostgreSQL service

```bash
cd /path/to/ruhusa-fastapi-smoke

docker compose up -d postgres
```

Output should show:
```
✓ Network ... created
✓ Container ... started
```

### 3. Verify PostgreSQL is ready

```bash
docker compose exec postgres pg_isready -U postgres
```

Expected output: `accepting connections`

If you get connection errors, wait a few seconds and try again. PostgreSQL takes ~5-10 seconds to fully start.

The `ruhusa_demo` database is automatically created by PostgreSQL from the `POSTGRES_DB` environment variable in `docker-compose.yml`. Ruhusa then initializes its schema and tables when it first connects.

### 4. Configure the DSN environment variable

The validation tests need to know how to connect to PostgreSQL:

```bash
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
```

**Components:**
- `postgres:postgres` = username:password (from `docker-compose.yml`)
- `localhost:5432` = host:port
- `ruhusa_demo` = database name (auto-created by Ruhusa schema init)

### 5. Run the complete validation suite

```bash
uv run pytest tests/ -v
```

This runs:
- ✓ 43 in-memory security tests
- ✓ 6 PostgreSQL integration tests
- ⊘ 1 skipped (tamper detection, requires isolated DB)

Expected result:
```
49 passed, 1 skipped in ~1s
```

### 6. Stop PostgreSQL when done

```bash
docker compose down
```

This stops and removes the container (data is in Docker volumes, won't be lost).

## Troubleshooting

### "Connection refused"

PostgreSQL is still starting. Wait 10 seconds and try again:

```bash
sleep 10
docker compose exec postgres pg_isready -U postgres
```

### "FATAL: database 'ruhusa_demo' does not exist"

Ruhusa schema initialization will create it automatically on first connection. If you see this error:

1. The DSN is correct (check spelling)
2. Wait a moment for initialization
3. Run tests again

### "Cannot connect to Docker daemon"

Docker isn't running. Start Docker Desktop (Mac/Windows) or the Docker service (Linux).

### Tests still fail with PostgreSQL errors

Check the logs:

```bash
docker compose logs postgres
```

### Want a fresh PostgreSQL database

The `docker-compose.yml` defines a named volume `postgres_data` that persists data across `docker compose down/up` cycles. 

To truly delete all data:

```bash
docker compose down -v
docker compose up -d postgres
```

The `-v` flag removes named volumes, creating a brand new, empty database.

**Data persistence:** By default, `docker compose down` preserves data in the `postgres_data` volume. Your test data survives container restarts.

**Data deletion:** Only `docker compose down -v` deletes the volume and all data.

## Running Specific Test Categories

### Only in-memory tests (fast)

```bash
uv run pytest tests/ -v -m "not postgres"
```

Result: 43 PASS in ~0.2s

### Only PostgreSQL tests

```bash
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
uv run pytest tests/ -v -m postgres
```

Result: 6 PASS, 1 SKIPPED in ~0.5s

### Specific test file

```bash
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
uv run pytest tests/test_durability.py -v
```

## Manual Testing with PostgreSQL

To test manually without pytest:

```bash
# Terminal 1: Start PostgreSQL
docker compose up -d postgres
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"

# Terminal 2: Start the app
uv run uvicorn app.main:app --reload

# Terminal 3: Test it
curl -X GET http://localhost:8000/health | jq .
# Should show: "ruhusa_backend": "postgres"

curl -X POST http://localhost:8000/refunds \
  -H "content-type: application/json" \
  -d '{"account_id":"test","amount":100,"principal_id":"billing-agent"}'
# Should execute successfully

# Terminal 1: Stop PostgreSQL
docker compose down
```

## Environment Variable Persistence

The `RUHUSA_POSTGRES_DSN` export only lasts for the current shell session.

### To make it permanent (macOS/Linux)

Add to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
```

Then reload:

```bash
source ~/.bashrc  # or ~/.zshrc
```

### To make it permanent (GitHub Actions)

It's already in `.github/workflows/validation.yml`:

```yaml
env:
  RUHUSA_POSTGRES_DSN: postgresql://postgres:postgres@localhost:5432/ruhusa_demo
```

## Next Time (Cursor Setup Instructions)

When validating a new Ruhusa release:

1. Update the version tag in `pyproject.toml`
2. Run this guide to set up PostgreSQL
3. Run `/validate-ruhusa-release` skill in Cursor
4. Review results in `RUHUSA_V0_7_VALIDATION.md`

The skill will automatically invoke the test suite you've just set up.
