# Ruhusa v0.7.0 External Validation Report

**Generated:** 2026-08-28T12:25:23.935344

**Report Type:** Automated pytest results (actual test execution)

---

## Test Execution Summary

### In-Memory Tests

| Result | Count |
|--------|-------|
| Passed | 43 |
| Failed | 0 |
| Skipped | 0 |
| Exit Code | 0 |
| **Status** | ✓ PASS |

### PostgreSQL Tests

| Result | Count |
|--------|-------|
| Configured | ✓ YES |
| Passed | 7 |
| Failed | 0 |
| Skipped | 1 |
| Exit Code | 0 |
| **Status** | ✓ PASS |

### Total

| Metric | Count |
|--------|-------|
| **Total Passed** | 50 |
| **Total Failed** | 0 |
| **Total Skipped** | 1 |

---

## Release Validation Verdict

### **PASS**

All security validation passed, including PostgreSQL integration.

### What Was Tested

✓ In-memory security validation: 43 tests

✓ PostgreSQL integration: 7 tests

### What Was NOT Tested



---

## How to Run

### In-Memory Tests Only

```bash
uv run pytest tests/ -v -m "not postgres"
```

### Full Validation (Requires PostgreSQL)

```bash
docker compose up -d postgres
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
uv run pytest tests/ -v
docker compose down
```

---

**Test Date:** 2026-08-28 12:25:23

**Verdict:** PASS

This report reflects actual test execution. Results are reproducible.
