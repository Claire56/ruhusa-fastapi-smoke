#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if PROJECT_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
fi

cd "$PROJECT_ROOT"

RESULTS_DIR="$PROJECT_ROOT/.validation-results"
REPORT="$PROJECT_ROOT/RUHUSA_V0_7_VALIDATION.md"

COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-ruhusa_validation_$$}"
RUHUSA_POSTGRES_PORT="${RUHUSA_POSTGRES_PORT:-55432}"
RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@127.0.0.1:${RUHUSA_POSTGRES_PORT}/ruhusa_demo"

export COMPOSE_PROJECT_NAME
export RUHUSA_POSTGRES_PORT

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

rm -rf "$RESULTS_DIR"
mkdir -p "$RESULTS_DIR"

uv sync

env -u RUHUSA_POSTGRES_DSN uv run pytest tests/ \
  -m "not postgres" \
  --tb=short \
  --junitxml="$RESULTS_DIR/in-memory.xml"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is required for mandatory PostgreSQL validation." >&2
  uv run python tests/report_generator.py \
    --junit-dir "$RESULTS_DIR" \
    --output "$REPORT" || true
  cat "$REPORT"
  exit 2
fi

docker compose up -d postgres

for _ in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U postgres -d ruhusa_demo >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker compose exec -T postgres pg_isready -U postgres -d ruhusa_demo >/dev/null 2>&1; then
  echo "PostgreSQL did not become healthy." >&2
  exit 1
fi

export RUHUSA_POSTGRES_DSN

uv run pytest tests/ \
  -m "postgres and not destructive_postgres and not tamper" \
  --tb=short \
  --junitxml="$RESULTS_DIR/postgres.xml"

RUHUSA_ALLOW_DESTRUCTIVE_TESTS=1 uv run pytest \
  tests/test_postgres_resilience.py \
  -m destructive_postgres \
  --tb=short \
  --junitxml="$RESULTS_DIR/resilience.xml"

RUHUSA_ALLOW_DESTRUCTIVE_TESTS=1 uv run pytest \
  tests/test_tamper.py \
  -m tamper \
  --tb=short \
  --junitxml="$RESULTS_DIR/tamper.xml"

set +e
uv run python tests/report_generator.py \
  --junit-dir "$RESULTS_DIR" \
  --output "$REPORT" \
  --ruhusa-version "v0.7.0" \
  --postgres-version "17"
REPORT_STATUS=$?
set -e

cat "$REPORT"
exit "$REPORT_STATUS"
