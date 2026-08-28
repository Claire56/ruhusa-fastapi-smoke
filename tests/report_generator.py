"""Generate validation report from actual pytest results (both in-memory and PostgreSQL)."""

import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path


def run_pytest_suite() -> dict:
    """Run both in-memory and PostgreSQL test suites, capture results."""
    
    results = {
        "in_memory": {"passed": 0, "failed": 0, "skipped": 0, "exit_code": 1},
        "postgres": {"passed": 0, "failed": 0, "skipped": 0, "exit_code": 1, "configured": False},
    }
    
    print("Executing pytest suites...")
    print("")
    
    # Run in-memory tests
    print("Running in-memory tests...")
    in_mem_result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "-m", "not postgres", "--tb=short"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )
    
    results["in_memory"] = parse_pytest_output(in_mem_result, is_postgres=False)
    print(f"  → {results['in_memory']['passed']} passed, {results['in_memory']['failed']} failed, {results['in_memory']['skipped']} skipped")
    
    # Run PostgreSQL tests if DSN is configured
    if os.getenv("RUHUSA_POSTGRES_DSN"):
        print("Running PostgreSQL tests...")
        
        postgres_result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "-m", "postgres", "--tb=short"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
            env={**os.environ, "RUHUSA_POSTGRES_DSN": os.getenv("RUHUSA_POSTGRES_DSN")},
        )
        
        results["postgres"] = parse_pytest_output(postgres_result, is_postgres=True)
        print(f"  → {results['postgres']['passed']} passed, {results['postgres']['failed']} failed, {results['postgres']['skipped']} skipped")
    else:
        print("PostgreSQL tests: NOT CONFIGURED (RUHUSA_POSTGRES_DSN not set)")
    
    print("")
    return results


def parse_pytest_output(result: subprocess.CompletedProcess, is_postgres: bool = False) -> dict:
    """Parse pytest output to extract test counts."""
    output = result.stdout + result.stderr
    
    summary = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "exit_code": result.returncode,
        "configured": is_postgres,
    }
    
    # Parse summary line: "43 passed, 8 deselected, 3 warnings in 1.20s"
    for line in output.split("\n"):
        if "passed" in line:
            # Extract number before "passed"
            import re
            passed_match = re.search(r'(\d+)\s+passed', line)
            if passed_match:
                summary["passed"] = int(passed_match.group(1))
            
            failed_match = re.search(r'(\d+)\s+failed', line)
            if failed_match:
                summary["failed"] = int(failed_match.group(1))
            
            skipped_match = re.search(r'(\d+)\s+skipped', line)
            if skipped_match:
                summary["skipped"] = int(skipped_match.group(1))
    
    return summary


def generate_report(results: dict) -> str:
    """Generate markdown report from actual test results."""
    in_mem = results["in_memory"]
    postgres = results["postgres"]
    
    # Calculate totals
    total_passed = in_mem["passed"] + postgres["passed"]
    total_failed = in_mem["failed"] + postgres["failed"]
    total_skipped = in_mem["skipped"] + postgres["skipped"]
    
    # Determine verdict
    in_mem_passed = in_mem["exit_code"] == 0 and in_mem["failed"] == 0
    has_skipped_mandatory = total_skipped > 0
    
    # Build list of NOT TESTED items
    not_tested = []
    if not postgres["configured"]:
        not_tested.append("PostgreSQL integration (RUHUSA_POSTGRES_DSN not configured)")
    if postgres["configured"] and postgres["skipped"] > 0:
        not_tested.append(f"Tamper detection ({postgres['skipped']} test skipped)")
    
    if postgres["configured"]:
        postgres_passed = postgres["exit_code"] == 0 and postgres["failed"] == 0
        all_passed = in_mem_passed and postgres_passed and not has_skipped_mandatory
        
        if total_failed > 0:
            verdict = "FAIL"
            verdict_detail = "Validation failed due to test failures. See test results below."
        elif all_passed:
            verdict = "PASS"
            verdict_detail = "All security validation passed, including PostgreSQL integration."
        else:
            verdict = "PASS WITH FINDINGS"
            verdict_detail = "Core security validation passed. Some mandatory integration tests were not executed (marked NOT TESTED below)."
    else:
        postgres_passed = False
        if total_failed > 0:
            verdict = "FAIL"
            verdict_detail = "In-memory validation failed. PostgreSQL tests not attempted."
        elif in_mem_passed:
            verdict = "PASS WITH FINDINGS"
            verdict_detail = "In-memory security validation passed. PostgreSQL integration NOT TESTED (RUHUSA_POSTGRES_DSN not configured)."
        else:
            verdict = "FAIL"
            verdict_detail = "In-memory validation failed. PostgreSQL tests not attempted."
    
    report = f"""# Ruhusa v0.7.0 External Validation Report

**Generated:** {datetime.now().isoformat()}

**Report Type:** Automated pytest results (actual test execution)

---

## Test Execution Summary

### In-Memory Tests

| Result | Count |
|--------|-------|
| Passed | {in_mem["passed"]} |
| Failed | {in_mem["failed"]} |
| Skipped | {in_mem["skipped"]} |
| Exit Code | {in_mem["exit_code"]} |
| **Status** | {"✓ PASS" if in_mem_passed else "✗ FAIL"} |

### PostgreSQL Tests

| Result | Count |
|--------|-------|
| Configured | {"✓ YES" if postgres["configured"] else "✗ NO"} |
| Passed | {postgres["passed"]} |
| Failed | {postgres["failed"]} |
| Skipped | {postgres["skipped"]} |
| Exit Code | {postgres["exit_code"]} |
| **Status** | {"✓ PASS" if postgres_passed else ("⊘ NOT TESTED" if not postgres["configured"] else "✗ FAIL")} |

### Total

| Metric | Count |
|--------|-------|
| **Total Passed** | {total_passed} |
| **Total Failed** | {total_failed} |
| **Total Skipped** | {total_skipped} |

---

## Release Validation Verdict

### **{verdict}**

{verdict_detail}

### What Was Tested

✓ In-memory security validation: {in_mem["passed"]} tests

{"✓ PostgreSQL integration: " + str(postgres["passed"]) + " tests" if postgres["configured"] else "⊘ PostgreSQL integration: NOT TESTED"}

### What Was NOT Tested

{("⊘ " + chr(10) + "⊘ ".join(not_tested)) if not_tested else "All mandatory tests were executed."}

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

**Test Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Verdict:** {verdict}

This report reflects actual test execution. Results are reproducible.
"""
    
    return report


if __name__ == "__main__":
    results = run_pytest_suite()
    report = generate_report(results)
    
    report_path = Path("RUHUSA_V0_7_VALIDATION.md")
    with open(report_path, "w") as f:
        f.write(report)
    
    print(report)
    print(f"\n✓ Report saved to: {report_path}")
