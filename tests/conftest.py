"""Shared fixtures for the Ruhusa v0.7.0 external validation suite."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app, refund_side_effects, runtime


@pytest.fixture(scope="session", autouse=True)
def check_postgres_availability() -> None:
    """Validate the configured PostgreSQL backend before postgres-marked tests."""
    dsn = os.getenv("RUHUSA_POSTGRES_DSN")
    if not dsn:
        return

    try:
        from ruhusa.postgres import create_postgres_pool, initialize_postgres_schema

        pool = create_postgres_pool(dsn, min_size=1, max_size=2, timeout=10)
        initialize_postgres_schema(pool)
        pool.close()
    except Exception as exc:
        pytest.skip(f"PostgreSQL not available: {exc}")


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def current_runtime():
    return runtime


@pytest.fixture
def clear_side_effects():
    refund_side_effects.clear()
    yield
    refund_side_effects.clear()


@pytest.fixture
def side_effect_count():
    def _count() -> int:
        return len(refund_side_effects)

    return _count


def pytest_collection_modifyitems(config, items) -> None:
    """Skip only tests whose required external backend was not configured."""
    dsn = os.getenv("RUHUSA_POSTGRES_DSN")

    for item in items:
        if "postgres" in item.keywords and not dsn:
            item.add_marker(
                pytest.mark.skip(reason="RUHUSA_POSTGRES_DSN not configured")
            )
