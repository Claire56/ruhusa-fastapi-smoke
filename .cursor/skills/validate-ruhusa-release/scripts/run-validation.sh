#!/bin/bash

# Ruhusa Release Validation Script
# This script validates a Ruhusa release against the validation matrix

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track validation results
PASSED=0
FAILED=0

# Helper functions
pass_check() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

fail_check() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++))
}

warn_check() {
    echo -e "${YELLOW}⚠${NC} $1"
}

echo "======================================"
echo "Ruhusa Release Validation"
echo "======================================"
echo ""

# Build Artifacts
echo "Checking build artifacts..."
if [ -d "${PROJECT_ROOT}/dist" ]; then
    pass_check "artifact-exists: dist/ directory found"
else
    warn_check "artifact-exists: dist/ directory not found"
fi

# Dependencies
echo ""
echo "Checking dependencies..."
if [ -f "${PROJECT_ROOT}/requirements.txt" ] || [ -f "${PROJECT_ROOT}/pyproject.toml" ]; then
    pass_check "deps-locked: Dependency file present"
else
    fail_check "deps-locked: No requirements.txt or pyproject.toml found"
fi

# Version Consistency
echo ""
echo "Checking version consistency..."
if [ -f "${PROJECT_ROOT}/pyproject.toml" ]; then
    PYPROJECT_VERSION=$(grep '^version' "${PROJECT_ROOT}/pyproject.toml" | head -1 | cut -d'"' -f2)
    if [ -n "$PYPROJECT_VERSION" ]; then
        pass_check "version-format: pyproject.toml version: $PYPROJECT_VERSION"
    else
        fail_check "version-format: Could not read version from pyproject.toml"
    fi
fi

# Tests
echo ""
echo "Checking tests..."
if [ -d "${PROJECT_ROOT}/tests" ]; then
    pass_check "tests-exist: tests/ directory found"
else
    warn_check "tests-exist: tests/ directory not found"
fi

# Documentation
echo ""
echo "Checking documentation..."
if [ -f "${PROJECT_ROOT}/CHANGELOG.md" ]; then
    pass_check "docs-complete: CHANGELOG.md found"
else
    warn_check "docs-complete: CHANGELOG.md not found"
fi

if [ -f "${PROJECT_ROOT}/README.md" ]; then
    pass_check "docs-readme: README.md found"
else
    warn_check "docs-readme: README.md not found"
fi

# Git Status
echo ""
echo "Checking git status..."
cd "${PROJECT_ROOT}"
if git rev-parse --git-dir > /dev/null 2>&1; then
    if [ -z "$(git status --porcelain)" ]; then
        pass_check "git-clean: Working directory is clean"
    else
        fail_check "git-clean: Working directory has uncommitted changes"
    fi
else
    warn_check "git-clean: Not in a git repository"
fi

# Summary
echo ""
echo "======================================"
echo "Validation Summary"
echo "======================================"
echo -e "Passed: ${GREEN}${PASSED}${NC}"
echo -e "Failed: ${RED}${FAILED}${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All validation checks passed!${NC}"
    exit 0
else
    echo -e "${RED}Some validation checks failed. Please review the errors above.${NC}"
    exit 1
fi
