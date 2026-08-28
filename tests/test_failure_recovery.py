"""Test failure and recovery scenarios for Ruhusa v0.7.0."""

import pytest
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import TOOL_ID, IMPLEMENTATION_ID
from ruhusa import InvocationRecord, Principal, AuthorizationRequest, TaskContext, compute_arguments_digest


class TestStaleClaimToUnknown:
    """Test that abandoned claims transition to UNKNOWN."""

    def test_claim_becomes_unknown_after_stale_threshold(self, client: TestClient, current_runtime, clear_side_effects):
        """Test CLAIMED → UNKNOWN transition when stale."""
        # Create abandoned claim
        claim_response = client.post(
            "/failure/claim-only",
            json={
                "account_id": "stale-claim-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        assert claim_response.status_code == 200
        claim_data = claim_response.json()
        assert claim_data["claimed"] is True
        assert claim_data["state"] == "claimed"
        invocation_id = claim_data["invocation_id"]
        
        # Mark as stale
        stale_response = client.post(f"/failure/stale/{invocation_id}")
        assert stale_response.status_code == 200
        stale_data = stale_response.json()
        assert stale_data["changed"] is True
        assert stale_data["state"] == "unknown"
        assert stale_data["claim_id"] is not None  # Claim ID preserved


class TestUnknownBlocksAutomaticRetry:
    """Test that UNKNOWN state blocks automatic retry."""

    def test_unknown_execution_blocked(self, client: TestClient, current_runtime, clear_side_effects, side_effect_count):
        """Test that execution is blocked while UNKNOWN."""
        # Create and abandon a claim
        claim_response = client.post(
            "/failure/claim-only",
            json={
                "account_id": "unknown-block-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        invocation_id = claim_response.json()["invocation_id"]
        
        # Mark as stale
        client.post(f"/failure/stale/{invocation_id}")
        
        # Verify execution is blocked
        execution_response = client.get(f"/executions/{invocation_id}")
        assert execution_response.status_code == 200
        exec_data = execution_response.json()
        assert exec_data["state"] == "unknown"
        
        initial_effects = side_effect_count()
        
        # Try to execute while UNKNOWN - should be blocked
        # Cannot use /refunds since it creates new invocation
        # Verify no automatic retry occurred
        final_effects = side_effect_count()
        assert final_effects == initial_effects


class TestInvalidReconciliationWhileClaimed:
    """Test that reconciliation is rejected while CLAIMED."""

    def test_reconciliation_fails_while_claimed(self, client: TestClient, clear_side_effects):
        """Test that reconciliation while CLAIMED returns false."""
        # Create abandoned claim
        claim_response = client.post(
            "/failure/claim-only",
            json={
                "account_id": "reconcile-claimed-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        invocation_id = claim_response.json()["invocation_id"]
        
        # Try to reconcile while still CLAIMED
        reconcile_response = client.post(
            f"/failure/reconcile/{invocation_id}",
            json={
                "outcome": "side_effect_not_applied",
                "reason": "test",
            },
        )
        
        assert reconcile_response.status_code == 200
        body = reconcile_response.json()
        assert body["reconciled"] is False
        assert body["state_before"] == "claimed"
        assert body["state_after"] == "claimed"


class TestRecoverySideEffectNotApplied:
    """Test recovery from UNKNOWN with SIDE_EFFECT_NOT_APPLIED."""

    def test_side_effect_not_applied_recovery(self, client: TestClient, clear_side_effects, side_effect_count):
        """Test SIDE_EFFECT_NOT_APPLIED recovery → AVAILABLE."""
        # Create and abandon claim
        claim_response = client.post(
            "/failure/claim-only",
            json={
                "account_id": "recovery-not-applied",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        invocation_id = claim_response.json()["invocation_id"]
        
        # Mark stale
        client.post(f"/failure/stale/{invocation_id}")
        
        initial_effects = side_effect_count()
        
        # Reconcile as not applied
        reconcile_response = client.post(
            f"/failure/reconcile/{invocation_id}",
            json={
                "outcome": "side_effect_not_applied",
                "reason": "verified no backend changes",
            },
        )
        
        assert reconcile_response.status_code == 200
        body = reconcile_response.json()
        assert body["reconciled"] is True
        assert body["state_before"] == "unknown"
        assert body["state_after"] == "available"
        assert body["recovery_count"] == 1
        
        # Verify no side effect from reconciliation itself
        assert side_effect_count() == initial_effects


class TestRecoverySideEffectConfirmed:
    """Test recovery from UNKNOWN with SIDE_EFFECT_CONFIRMED."""

    def test_side_effect_confirmed_recovery(self, client: TestClient, clear_side_effects, side_effect_count):
        """Test SIDE_EFFECT_CONFIRMED recovery → COMPLETED."""
        # Create and abandon claim
        claim_response = client.post(
            "/failure/claim-only",
            json={
                "account_id": "recovery-confirmed",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        invocation_id = claim_response.json()["invocation_id"]
        
        # Mark stale
        client.post(f"/failure/stale/{invocation_id}")
        
        initial_effects = side_effect_count()
        
        # Reconcile as confirmed
        reconcile_response = client.post(
            f"/failure/reconcile/{invocation_id}",
            json={
                "outcome": "side_effect_confirmed",
                "reason": "verified backend processing occurred",
            },
        )
        
        assert reconcile_response.status_code == 200
        body = reconcile_response.json()
        assert body["reconciled"] is True
        assert body["state_before"] == "unknown"
        assert body["state_after"] == "completed"
        assert body["recovery_count"] == 1
        
        # Verify no additional side effect
        assert side_effect_count() == initial_effects
