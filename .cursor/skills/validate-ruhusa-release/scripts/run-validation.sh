#!/bin/bash

# Ruhusa Release Validation Script
# Executes the automated pytest validation suite against Ruhusa release

set -e

# Get the actual repository root (not .cursor directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "${SKILL_DIR}/../../.." && pwd)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================"
echo "Ruhusa Release Validation"
echo "======================================"
echo ""
echo "Project root: ${PROJECT_ROOT}"
echo ""

# Verify we're in a git repository with Ruhusa pinned
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} Not in a git repository"
    exit 1
fi

cd "${PROJECT_ROOT}"

# Check Ruhusa version
echo "Detecting Ruhusa version..."
if [ -f "pyproject.toml" ]; then
    RUHUSA_VERSION=$(grep 'tag = "v' pyproject.toml | sed 's/.*tag = "\(v[^"]*\)".*/\1/')
    if [ -n "$RUHUSA_VERSION" ]; then
        echo -e "${GREEN}✓${NC} Ruhusa version: $RUHUSA_VERSION"
    else
        echo -e "${RED}✗${NC} Could not detect Ruhusa version from pyproject.toml"
        exit 1
    fi
fi

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓${NC} Python: $PYTHON_VERSION"

# Check dependencies
echo ""
echo "Running in-memory test suite..."
if python3 -m pytest tests/ -v -m "not postgres" --tb=short 2>&1; then
    echo -e "${GREEN}✓${NC} In-memory tests passed"
else
    echo -e "${RED}✗${NC} In-memory tests failed"
    exit 1
fi

# PostgreSQL tests (optional)
echo ""
echo "PostgreSQL tests (if RUHUSA_POSTGRES_DSN configured)..."
if [ -n "$RUHUSA_POSTGRES_DSN" ]; then
    if python3 -m pytest tests/ -v -m postgres --tb=short 2>&1; then
        echo -e "${GREEN}✓${NC} PostgreSQL tests passed"
    else
        echo -e "${YELLOW}⚠${NC} PostgreSQL tests had issues"
    fi
else
    echo -e "${YELLOW}⊘${NC} RUHUSA_POSTGRES_DSN not set; PostgreSQL tests skipped"
fi

echo ""
echo "======================================"
echo -e "${GREEN}Validation suite executed${NC}"
echo "======================================"
echo "See RUHUSA_V0_7_VALIDATION.md for detailed results"
exit 0
