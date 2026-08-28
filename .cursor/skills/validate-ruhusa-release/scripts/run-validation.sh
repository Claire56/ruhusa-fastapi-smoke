#!/bin/bash

# Ruhusa Release Validation Script
# Executes the automated pytest validation suite against Ruhusa release

# Get the actual repository root (4 levels up from this script)
# .cursor/skills/validate-ruhusa-release/scripts/run-validation.sh → repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

echo "======================================"
echo "Ruhusa Release Validation"
echo "======================================"
echo ""
echo "Project root: ${PROJECT_ROOT}"
echo ""

# Verify we're in a git repository
cd "${PROJECT_ROOT}" || exit 1

if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "✗ Not in a git repository"
    exit 1
fi

# Check Ruhusa version
echo "Detecting Ruhusa version..."
if [ -f "pyproject.toml" ]; then
    RUHUSA_VERSION=$(grep 'tag = "v' pyproject.toml | head -1 | sed 's/.*tag = "\(v[^"]*\)".*/\1/')
    if [ -n "$RUHUSA_VERSION" ]; then
        echo "✓ Ruhusa version: $RUHUSA_VERSION"
    else
        echo "✗ Could not detect Ruhusa version from pyproject.toml"
        exit 1
    fi
fi

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python: $PYTHON_VERSION"

# Run in-memory test suite
echo ""
echo "Running in-memory test suite..."
if uv run pytest tests/ -v -m "not postgres" --tb=short; then
    echo "✓ In-memory tests passed"
else
    echo "✗ In-memory tests failed"
    exit 1
fi

# PostgreSQL tests (optional)
echo ""
echo "PostgreSQL tests (if RUHUSA_POSTGRES_DSN configured)..."
if [ -n "$RUHUSA_POSTGRES_DSN" ]; then
    if uv run pytest tests/ -v -m postgres --tb=short; then
        echo "✓ PostgreSQL tests passed"
    else
        echo "✗ PostgreSQL tests had failures"
        exit 1
    fi
else
    echo "⊘ RUHUSA_POSTGRES_DSN not set; PostgreSQL tests skipped"
fi

# Generate report
echo ""
echo "Generating validation report..."
uv run python tests/report_generator.py

echo ""
echo "======================================"
echo "✓ Validation suite executed"
echo "======================================"
echo "See RUHUSA_V0_7_VALIDATION.md for results"
exit 0
