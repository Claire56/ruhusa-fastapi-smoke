"""Advanced concurrency tests for Ruhusa v0.7.0."""

import concurrent.futures
import pytest
from fastapi.testclient import TestClient


class TestConcurrentReconciliation:
    """Test that only one reconciliation succeeds under concurrency."""

    def test_concurrent_reconciliation_single_winner(self, client: TestClient, clear_side_effects):
        """Test that only one concurrent reconciliation succeeds."""
        # Create and abandon claim
        claim_response = client.post(
            "/failure/claim-only",
            json={
                "account_id": "concurrent-reconcile",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        invocation_id = claim_response.json()["invocation_id"]
        
        # Mark stale
        client.post(f"/failure/stale/{invocation_id}")
        
        # Launch concurrent reconciliation attempts
        def concurrent_reconcile(attempt_id):
            client_instance = TestClient(client.app)
            response = client_instance.post(
                f"/failure/reconcile/{invocation_id}",
                json={
                    "outcome": "side_effect_not_applied",
                    "reason": f"concurrent attempt {attempt_id}",
                },
            )
            return response.json()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(concurrent_reconcile, range(5)))
        
        # Only one should succeed
        successes = [r for r in results if r.get("reconciled") is True]
        assert len(successes) == 1
        
        # Final recovery_count should be exactly 1
        assert successes[0]["recovery_count"] == 1


@pytest.mark.postgres
class TestAuditConcurrency:
    """Test audit chain integrity under concurrent load."""

    def test_audit_chain_under_concurrent_load(self, client: TestClient, clear_side_effects):
        """Test that concurrent authorization requests maintain chain integrity."""
        # Generate concurrent refunds
        def concurrent_refund(account_id):
            client_instance = TestClient(client.app)
            response = client_instance.post(
                "/refunds",
                json={
                    "account_id": f"concurrent-audit-{account_id}",
                    "amount": 50,
                    "principal_id": "billing-agent",
                },
            )
            return response.status_code == 200
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(concurrent_refund, range(10)))
        
        # All should succeed
        assert all(results)
        
        # Verify chain integrity
        audit_response = client.get("/audit")
        assert audit_response.status_code == 200
        audit = audit_response.json()
        assert audit["count"] >= 10
        assert audit["chain_valid"] is True
