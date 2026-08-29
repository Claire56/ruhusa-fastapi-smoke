"""Helpers for destructive tests against an isolated Docker Compose PostgreSQL."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def require_destructive_opt_in() -> None:
    if os.getenv("RUHUSA_ALLOW_DESTRUCTIVE_TESTS") != "1":
        raise RuntimeError(
            "Destructive PostgreSQL tests require RUHUSA_ALLOW_DESTRUCTIVE_TESTS=1"
        )


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def wait_for_postgres(timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    last = ""

    while time.monotonic() < deadline:
        result = compose(
            "exec",
            "-T",
            "postgres",
            "pg_isready",
            "-U",
            "postgres",
            "-d",
            "ruhusa_demo",
            check=False,
        )
        last = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            return
        time.sleep(1)

    raise AssertionError(f"PostgreSQL did not become healthy: {last}")


def wait_for_http_health(client, timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    last_status = None

    while time.monotonic() < deadline:
        response = client.get("/health")
        last_status = response.status_code
        if response.status_code == 200:
            body = response.json()
            if body.get("ruhusa_backend") == "postgres":
                return
        time.sleep(1)

    raise AssertionError(
        f"FastAPI/Ruhusa pool did not recover; last health status={last_status}"
    )
