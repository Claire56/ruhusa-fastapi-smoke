"""Destructive PostgreSQL outage/restart tests.

Run only against the isolated Docker Compose database created by the validation
script or dedicated CI job.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app, refund_side_effects, runtime
from tests.postgres_control import (
    compose,
    require_destructive_opt_in,
    wait_for_http_health,
    wait_for_postgres,
)


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.destructive_postgres,
]


@pytest.fixture(autouse=True)
def destructive_guard():
    require_destructive_opt_in()
    assert runtime.backend == "postgres"
    refund_side_effects.clear()
    yield
    compose("start", "postgres", check=False)
    try:
        wait_for_postgres()
    finally:
        refund_side_effects.clear()


def test_database_outage_blocks_protected_side_effect_and_pool_recovers():
    """No trusted security state means no refund; restored DB recovers in-place."""
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        before = len(refund_side_effects)

        compose("stop", "postgres")
        outage_response = client.post(
            "/refunds",
            json={
                "account_id": "db-outage-validation",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )

        assert outage_response.status_code >= 500
        assert len(refund_side_effects) == before

        compose("start", "postgres")
        wait_for_postgres()
        wait_for_http_health(client)

        recovery = client.post(
            "/refunds",
            json={
                "account_id": "db-recovery-validation",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )

        assert recovery.status_code == 200
        recovery_body = recovery.json()
        assert recovery_body["executed"] is True
        assert recovery_body["execution_state"] == "completed"
        assert len(refund_side_effects) == before + 1


def test_postgres_container_restart_preserves_execution_and_audit_state():
    """Restart the actual DB container, then verify durable state from a fresh pool."""
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/refunds",
            json={
                "account_id": "postgres-restart-validation",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        assert response.status_code == 200
        body = response.json()
        invocation_id = body["invocation_id"]
        audit_id = body["audit_id"]

        original = runtime.execution_store.get(invocation_id)
        assert original is not None
        assert original.state.value == "completed"
        original_claim_id = original.claim_id

        compose("restart", "postgres")
        wait_for_postgres()
        wait_for_http_health(client)

        from ruhusa.postgres import (
            PostgresAuditLog,
            PostgresExecutionStore,
            create_postgres_pool,
            initialize_postgres_schema,
        )

        dsn = os.environ["RUHUSA_POSTGRES_DSN"]
        fresh_pool = create_postgres_pool(
            dsn,
            min_size=1,
            max_size=2,
            timeout=10,
        )
        try:
            initialize_postgres_schema(fresh_pool)

            execution_store = PostgresExecutionStore(fresh_pool)
            audit_log = PostgresAuditLog(fresh_pool)

            restored = execution_store.get(invocation_id)
            assert restored is not None
            assert restored.state.value == "completed"
            assert restored.attempt_count == 1
            assert restored.claim_id == original_claim_id

            assert audit_log.get(audit_id) is not None
            assert audit_log.verify_chain() is True
        finally:
            fresh_pool.close()
