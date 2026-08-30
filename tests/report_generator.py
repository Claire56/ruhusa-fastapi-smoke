"""Build a release-validation report from pytest JUnit XML artifacts.

The generator never re-runs tests and never hardcodes PASS. A full PASS requires
all mandatory validation lanes to be present with zero failures, errors, or
skips.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET


MANDATORY_LANES = {
    "in-memory": "Authorization, provenance, execution, replay, recovery",
    "postgres": "Durable PostgreSQL stores and concurrency",
    "resilience": "Real PostgreSQL outage/recovery and container restart",
    "tamper": "Audit hash-chain tamper evidence",
}


@dataclass
class Counts:
    tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0

    def add(self, other: "Counts") -> None:
        self.tests += other.tests
        self.passed += other.passed
        self.failed += other.failed
        self.errors += other.errors
        self.skipped += other.skipped


def classify(path: Path) -> str | None:
    name = path.name.lower()
    for lane in MANDATORY_LANES:
        if name.startswith(lane):
            return lane
    return None


def counts_from_junit(path: Path) -> Counts:
    root = ET.parse(path).getroot()
    testcases = list(root.iter("testcase"))

    failed = 0
    errors = 0
    skipped = 0

    for case in testcases:
        if case.find("failure") is not None:
            failed += 1
        elif case.find("error") is not None:
            errors += 1
        elif case.find("skipped") is not None:
            skipped += 1

    tests = len(testcases)
    passed = tests - failed - errors - skipped

    return Counts(
        tests=tests,
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
    )


def build_report(junit_dir: Path, ruhusa_version: str, postgres_version: str) -> tuple[str, int]:
    xml_files = sorted(junit_dir.rglob("*.xml"))

    lanes = {lane: Counts() for lane in MANDATORY_LANES}
    lane_files = {lane: [] for lane in MANDATORY_LANES}

    ignored = []

    for path in xml_files:
        lane = classify(path)
        if lane is None:
            ignored.append(path.name)
            continue
        counts = counts_from_junit(path)
        lanes[lane].add(counts)
        lane_files[lane].append(path.name)

    missing = [lane for lane, files in lane_files.items() if not files]

    total = Counts()
    for counts in lanes.values():
        total.add(counts)

    has_failures = total.failed > 0 or total.errors > 0
    has_skips = total.skipped > 0

    if has_failures or missing:
        verdict = "FAIL"
        exit_code = 1
    elif has_skips:
        verdict = "PASS WITH FINDINGS"
        exit_code = 2
    else:
        verdict = "PASS"
        exit_code = 0

    rows = []
    for lane, security_property in MANDATORY_LANES.items():
        counts = lanes[lane]
        if not lane_files[lane]:
            status = "NOT TESTED"
        elif counts.failed or counts.errors:
            status = "FAIL"
        elif counts.skipped:
            status = "PASS WITH FINDINGS"
        else:
            status = "PASS"

        rows.append(
            f"| {lane} | {security_property} | {counts.tests} | "
            f"{counts.passed} | {counts.failed + counts.errors} | "
            f"{counts.skipped} | **{status}** |"
        )

    not_tested = (
        "\n".join(f"- `{lane}`: mandatory lane did not produce JUnit evidence" for lane in missing)
        if missing
        else "- None"
    )

    skipped_note = (
        f"- {total.skipped} test(s) were skipped and therefore were not fully validated."
        if total.skipped
        else "- None"
    )

    report = f"""# Ruhusa v0.7.0 External Validation Report

**Generated:** {datetime.now(UTC).isoformat()}  
**Ruhusa target:** {ruhusa_version}  
**Python running report generator:** {platform.python_version()}  
**PostgreSQL target:** {postgres_version}

## Verdict

# **{verdict}**

A full **PASS** is emitted only when every mandatory validation lane produced
JUnit evidence and there were zero failures, errors, or skipped tests.

## Validation lanes

| Lane | Security property | Tests | Passed | Failed/Error | Skipped | Result |
|---|---|---:|---:|---:|---:|---|
{chr(10).join(rows)}

## Totals

| Metric | Count |
|---|---:|
| Tests | {total.tests} |
| Passed | {total.passed} |
| Failed | {total.failed} |
| Errors | {total.errors} |
| Skipped | {total.skipped} |

## What was NOT tested

{not_tested}

## Findings

{skipped_note}

## Evidence files

{chr(10).join(f"- `{path.name}`" for path in xml_files) if xml_files else "- None"}

## Validation contract

The suite is an external-consumer validation of the released Ruhusa package.
It does not modify Ruhusa and does not treat HTTP status alone as security
evidence. Protected side-effect invariants are asserted in authorization,
replay, concurrency, UNKNOWN, recovery, and database-outage tests.
"""

    return report, exit_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ruhusa-version", default="v0.7.0")
    parser.add_argument("--postgres-version", default="17")
    args = parser.parse_args()

    report, exit_code = build_report(
        args.junit_dir,
        args.ruhusa_version,
        args.postgres_version,
    )

    if args.output:
        args.output.write_text(report)
    else:
        print(report)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
