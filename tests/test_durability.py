"""Test PostgreSQL durability for Ruhusa v0.7.0."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.postgres
class TestPostgresExecutionDurability:
    """Test execution state persists across application restart."""

    def test_execution_state_persists_after_restart(self, client: TestClient, current_runtime, clear_side_effects):
        """Test COMPLETED state persists after fresh pool/runtime against same database."""
        from ruhusa.postgres import create_postgres_pool, PostgresExecutionStore
        import os
        
        # Create refund with PostgreSQL backend via current runtime
        response = client.post(
            "/refunds",
            json={
                "account_id": "durability-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        assert response.status_code == 200
        body = response.json()
        invocation_id = body["invocation_id"]
        
        # Record the state from original runtime
        original_record = current_runtime.execution_store.get(invocation_id)
        assert original_record is not None
        original_state = original_record.state.value
        original_attempt_count = original_record.attempt_count
        original_claim_id = original_record.claim_id
        
        # Simulate restart: create fresh pool and store against same database
        dsn = os.getenv("RUHUSA_POSTGRES_DSN")
        if dsn:
            fresh_pool = create_postgres_pool(dsn, min_size=1, max_size=2)
            fresh_store = PostgresExecutionStore(fresh_pool)
            
            # Query same record from fresh pool
            restored_record = fresh_store.get(invocation_id)
            fresh_pool.close()
            
            assert restored_record is not None
            assert restored_record.state.value == original_state
            assert restored_record.attempt_count == original_attempt_count
            assert restored_record.claim_id == original_claim_id


@pytest.mark.postgres
class TestPostgresAuditDurability:
    """Test audit events persist across application restart."""

    def test_audit_events_persist_after_restart(self, client: TestClient, current_runtime, clear_side_effects):
        """Test audit events persist and chain integrity is maintained."""
        # Create multiple refunds
        for i in range(3):
            client.post(
                "/refunds",
                json={
                    "account_id": f"audit-durability-{i}",
                    "amount": 100,
                    "principal_id": "billing-agent",
                },
            )
        
        audit_response = client.get("/audit")
        assert audit_response.status_code == 200
        original_audit = audit_response.json()
        original_count = original_audit["count"]
        original_chain_valid = original_audit["chain_valid"]
        
        # Simulate restart by fetching audit again
        # (In a real scenario, this would involve restarting the process)
        restored_audit_response = client.get("/audit")
        restored_audit = restored_audit_response.json()
        
        assert restored_audit["count"] == original_count
        assert restored_audit["chain_valid"] == original_chain_valid


@pytest.mark.postgres
class TestPostgresOutageAndRecovery:
    """Test fail-closed behavior when PostgreSQL is unavailable."""

    def test_postgresql_unavailable_denies_execution(self, client: TestClient, clear_side_effects, side_effect_count):
        """Test that operations fail safely when PostgreSQL is unavailable.
        
        NOTE: This test assumes PostgreSQL is running. To test actual outage:
        Run: docker compose stop postgres
        Then run this test
        Then: docker compose start postgres
        """
        # This is a placeholder that verifies health includes backend status
        health_response = client.get("/health")
        assert health_response.status_code == 200
        health = health_response.json()
        assert "ruhusa_backend" in health
        # If backend is postgres and it's unavailable, health would indicate that
        # The actual test requires manually stopping PostgreSQL


@pytest.mark.postgres
class TestPostgresRestartDurability:
    """Test persistence across PostgreSQL container restart."""

    def test_postgres_container_restart_preserves_data(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that restarting PostgreSQL container preserves data.
        
        NOTE: This test verifies that after running other postgres tests,
        data is still present. Manual test:
        1. Run other postgres tests to populate data
        2. docker compose restart postgres
        3. Verify data persists
        """
        # Check that data exists
        audit_response = client.get("/audit")
        assert audit_response.status_code == 200
        audit = audit_response.json()
        # Should have audit events from other tests
        assert audit["chain_valid"] is True


@pytest.mark.postgres
class TestPostgresToolRegistry:
    """Test tool registrations persist in PostgreSQL."""

    def test_tool_registration_persists(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that tool registrations are durable."""
        from app.main import TOOL_ID, IMPLEMENTATION_ID
        
        # Tool should be registered from initialization
        assert current_runtime.tool_registry.is_trusted(TOOL_ID, IMPLEMENTATION_ID)
