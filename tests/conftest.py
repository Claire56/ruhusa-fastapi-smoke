"""Pytest configuration and fixtures for Ruhusa v0.7.0 validation suite."""

import os
import subprocess
import time
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app, build_runtime, runtime


@pytest.fixture(scope="session", autouse=True)
def check_postgres_availability():
    """Check PostgreSQL is available for postgres-marked tests."""
    dsn = os.getenv("RUHUSA_POSTGRES_DSN")
    
    # If DSN is not set, postgres tests will be skipped
    if not dsn:
        return
    
    # Try to connect and verify schema
    try:
        from ruhusa.postgres import create_postgres_pool, initialize_postgres_schema
        
        pool = create_postgres_pool(dsn, min_size=1, max_size=2)
        initialize_postgres_schema(pool)
        pool.close()
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provide a fresh test client for each test."""
    yield TestClient(app)


@pytest.fixture
def current_runtime():
    """Provide access to the current runtime (memory or postgres)."""
    return runtime


@pytest.fixture
def clear_side_effects():
    """Clear the side effects list before each test."""
    from app.main import refund_side_effects
    refund_side_effects.clear()
    yield
    refund_side_effects.clear()


@pytest.fixture
def side_effect_count():
    """Return a function that counts current side effects."""
    def _count():
        from app.main import refund_side_effects
        return len(refund_side_effects)
    return _count


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "postgres: mark test as requiring PostgreSQL backend"
    )


def pytest_collection_modifyitems(config, items):
    """Add postgres marker to tests that need it, skip if PostgreSQL not available."""
    dsn = os.getenv("RUHUSA_POSTGRES_DSN")
    
    for item in items:
        if "postgres" in item.keywords:
            if not dsn:
                item.add_marker(
                    pytest.mark.skip(reason="RUHUSA_POSTGRES_DSN not configured")
                )
