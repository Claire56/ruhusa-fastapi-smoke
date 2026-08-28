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
class TestPostgresExecutionConcurrency:
    """Test PostgreSQL execution concurrency: 20 callers, same invocation, exactly 1 winner."""
    
    def test_postgres_concurrent_single_winner_25_rounds(self, client: TestClient, clear_side_effects, side_effect_count):
        """Test 20 concurrent callers against same invocation for 25 rounds."""
        for round_num in range(25):
            # Prepare fresh invocation for each round
            prep_response = client.post(
                "/concurrency/prepare",
                json={
                    "account_id": f"postgres-concurrency-round-{round_num}",
                    "amount": 100,
                    "principal_id": "billing-agent",
                },
            )
            
            assert prep_response.status_code == 200
            test_data = prep_response.json()
            invocation_id = test_data["invocation_id"]
            
            # 20 concurrent callers
            def concurrent_attempt(caller_id):
                client_instance = TestClient(client.app)
                response = client_instance.post(
                    f"/concurrency/{invocation_id}",
                    json={
                        "account_id": test_data["account_id"],
                        "amount": test_data["amount"],
                        "principal_id": test_data["principal_id"],
                    },
                )
                return response.json() if response.status_code in (200, 409) else None
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                results = list(executor.map(concurrent_attempt, range(20)))
            
            # Verify exactly 1 winner per round
            winners = [r for r in results if r and r.get("winner") is True]
            assert len(winners) == 1, f"Round {round_num}: expected 1 winner, got {len(winners)}"
            
            # Verify exactly 1 side effect per round
            expected_count = round_num + 1
            assert side_effect_count() == expected_count


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
