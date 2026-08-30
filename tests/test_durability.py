"""Non-destructive PostgreSQL durability tests for Ruhusa v0.7.0."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.postgres


def _dsn() -> str:
    value = os.getenv("RUHUSA_POSTGRES_DSN")
    assert value, "RUHUSA_POSTGRES_DSN must be set for PostgreSQL tests"
    return value


def test_execution_invocation_audit_and_tool_state_survive_fresh_pool(
    client: TestClient,
    current_runtime,
    clear_side_effects,
):
    """A new pool/store set must observe state written by the running app."""
    assert current_runtime.backend == "postgres"

    response = client.post(
        "/refunds",
        json={
            "account_id": "fresh-pool-durability",
            "amount": 100,
            "principal_id": "billing-agent",
        },
    )
    assert response.status_code == 200
    body = response.json()

    invocation_id = body["invocation_id"]
    audit_id = body["audit_id"]

    original_execution = current_runtime.execution_store.get(invocation_id)
    assert original_execution is not None
    assert original_execution.state.value == "completed"
    assert original_execution.attempt_count == 1

    from app.main import IMPLEMENTATION_ID, TOOL_ID
    from ruhusa.postgres import (
        PostgresAuditLog,
        PostgresExecutionStore,
        PostgresInvocationStore,
        PostgresToolRegistry,
        create_postgres_pool,
        initialize_postgres_schema,
    )

    fresh_pool = create_postgres_pool(_dsn(), min_size=1, max_size=2, timeout=10)
    try:
        initialize_postgres_schema(fresh_pool)

        execution_store = PostgresExecutionStore(fresh_pool)
        invocation_store = PostgresInvocationStore(fresh_pool)
        audit_log = PostgresAuditLog(fresh_pool)
        tool_registry = PostgresToolRegistry(fresh_pool)

        restored_execution = execution_store.get(invocation_id)
        assert restored_execution is not None
        assert restored_execution.state.value == "completed"
        assert restored_execution.attempt_count == 1
        assert restored_execution.claim_id == original_execution.claim_id

        restored_invocation = invocation_store.get(invocation_id)
        assert restored_invocation is not None
        assert restored_invocation.invocation_id == invocation_id
        assert restored_invocation.executing_principal_id == "billing-agent"

        restored_audit = audit_log.get(audit_id)
        assert restored_audit is not None
        assert restored_audit.audit_id == audit_id
        assert audit_log.verify_chain() is True

        assert tool_registry.is_trusted(TOOL_ID, IMPLEMENTATION_ID) is True
    finally:
        fresh_pool.close()


def test_audit_history_survives_fresh_audit_instance(
    client: TestClient,
    current_runtime,
    clear_side_effects,
):
    assert current_runtime.backend == "postgres"

    response = client.post(
        "/refunds",
        json={
            "account_id": "audit-fresh-instance",
            "amount": 100,
            "principal_id": "billing-agent",
        },
    )
    assert response.status_code == 200
    audit_id = response.json()["audit_id"]

    from ruhusa.postgres import (
        PostgresAuditLog,
        create_postgres_pool,
        initialize_postgres_schema,
    )

    fresh_pool = create_postgres_pool(_dsn(), min_size=1, max_size=2, timeout=10)
    try:
        initialize_postgres_schema(fresh_pool)
        fresh_audit = PostgresAuditLog(fresh_pool)

        assert fresh_audit.get(audit_id) is not None
        assert fresh_audit.verify_chain() is True

        snapshot = fresh_audit.snapshot()
        assert any(event.audit_id == audit_id for event in snapshot)
    finally:
        fresh_pool.close()
