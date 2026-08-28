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
        """Test that execution attempt is rejected while UNKNOWN."""
        from datetime import UTC, datetime, timedelta
        from uuid import uuid4
        from ruhusa import InvocationRecord, Principal, AuthorizationRequest, TaskContext, compute_arguments_digest
        from app.main import TOOL_ID, IMPLEMENTATION_ID
        
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
        
        # Mark as stale → UNKNOWN
        client.post(f"/failure/stale/{invocation_id}")
        
        # Verify state is UNKNOWN
        execution_response = client.get(f"/executions/{invocation_id}")
        assert execution_response.status_code == 200
        exec_data = execution_response.json()
        assert exec_data["state"] == "unknown"
        
        initial_effects = side_effect_count()
        
        # Attempt execution while UNKNOWN - must be rejected
        now = datetime.now(UTC)
        canonical = current_runtime.invocation_store.get(invocation_id)
        
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource=f"account/unknown-block-test",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=canonical.task_id,
                initiated_by="test",
                purpose="retry during UNKNOWN",
                expires_at=canonical.expires_at,
            ),
            invocation_id=invocation_id,
        )
        
        # Attempt to begin() while UNKNOWN
        begin = current_runtime.controller.begin(request, now=now)
        
        # Must be rejected
        assert begin.allowed is False
        
        # Verify no side effect occurred
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

    def test_side_effect_not_applied_recovery_and_attempt_2(self, client: TestClient, clear_side_effects, side_effect_count):
        """Test SIDE_EFFECT_NOT_APPLIED → AVAILABLE → attempt 2 can execute."""
        # Create and abandon claim
        claim_response = client.post(
            "/failure/claim-only",
            json={
                "account_id": "recovery-not-applied-attempt2",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        invocation_id = claim_response.json()["invocation_id"]
        
        # Mark stale → UNKNOWN
        client.post(f"/failure/stale/{invocation_id}")
        
        initial_effects = side_effect_count()
        
        # Reconcile as not applied → AVAILABLE
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
        
        # Verify no side effect from reconciliation
        assert side_effect_count() == initial_effects
        
        # Attempt 2: make a fresh refund request on the same account
        # This verifies that recovery to AVAILABLE allows new execution
        attempt2_response = client.post(
            "/refunds",
            json={
                "account_id": "recovery-not-applied-attempt2",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        # Fresh invocation should succeed (different invocation_id)
        assert attempt2_response.status_code == 200
        
        # Verify side effect occurred (total should be 1, not 0)
        final_effects = side_effect_count()
        assert final_effects == initial_effects + 1


class TestRecoverySideEffectConfirmed:
    """Test recovery from UNKNOWN with SIDE_EFFECT_CONFIRMED."""

    def test_side_effect_confirmed_recovery_blocks_retry(self, client: TestClient, current_runtime, clear_side_effects, side_effect_count):
        """Test SIDE_EFFECT_CONFIRMED recovery → COMPLETED → retry blocked."""
        from datetime import UTC, datetime, timedelta
        from ruhusa import Principal, AuthorizationRequest, TaskContext
        
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
        canonical = current_runtime.invocation_store.get(invocation_id)
        
        # Mark stale → UNKNOWN
        client.post(f"/failure/stale/{invocation_id}")
        
        initial_effects = side_effect_count()
        
        # Reconcile as confirmed → COMPLETED
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
        
        # Attempt to retry while COMPLETED - must be blocked
        now = datetime.now(UTC)
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource=f"account/recovery-confirmed",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=canonical.task_id,
                initiated_by="test",
                purpose="retry after confirmed",
                expires_at=canonical.expires_at,
            ),
            invocation_id=invocation_id,
        )
        
        # Attempt begin() after COMPLETED
        begin = current_runtime.controller.begin(request, now=now)
        
        # Must be blocked (already completed)
        assert begin.allowed is False
        
        # Verify no additional side effect
        assert side_effect_count() == initial_effects


class TestRecoveryAuthorizationBypass:
    """Test that recovery does not bypass authorization checks."""

    def test_recovery_followed_by_expired_task_denied(self, client: TestClient, current_runtime, clear_side_effects, side_effect_count):
        """Test that recovery → AVAILABLE doesn't execute if task expires."""
        from datetime import UTC, datetime, timedelta
        from ruhusa import Principal, AuthorizationRequest, TaskContext
        
        # Create and abandon claim
        claim_response = client.post(
            "/failure/claim-only",
            json={
                "account_id": "recovery-expired",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        invocation_id = claim_response.json()["invocation_id"]
        canonical = current_runtime.invocation_store.get(invocation_id)
        
        # Mark stale
        client.post(f"/failure/stale/{invocation_id}")
        
        initial_effects = side_effect_count()
        
        # Reconcile → AVAILABLE
        reconcile_response = client.post(
            f"/failure/reconcile/{invocation_id}",
            json={
                "outcome": "side_effect_not_applied",
                "reason": "verified no changes",
            },
        )
        
        assert reconcile_response.status_code == 200
        assert reconcile_response.json()["state_after"] == "available"
        
        # Now attempt execution with EXPIRED task
        now = datetime.now(UTC)
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource=f"account/recovery-expired",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=canonical.task_id,
                initiated_by="test",
                purpose="attempt with expired task",
                expires_at=now - timedelta(minutes=1),  # Task expired
            ),
            invocation_id=invocation_id,
        )
        
        # Should be denied due to expired task, even though recovered to AVAILABLE
        begin = current_runtime.controller.begin(request, now=now)
        assert begin.allowed is False
        
        # Verify no side effect
        assert side_effect_count() == initial_effects
