"""Test failure and recovery scenarios for Ruhusa v0.7.0."""

import pytest
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import TOOL_ID, IMPLEMENTATION_ID
from ruhusa import InvocationRecord, Principal, AuthorizationRequest, TaskContext, compute_arguments_digest, ExecutionRecoveryOutcome


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

    def test_side_effect_not_applied_recovery_and_attempt_2(self, client: TestClient, current_runtime, clear_side_effects, side_effect_count):
        """Test SIDE_EFFECT_NOT_APPLIED → AVAILABLE → attempt 2 → COMPLETED."""
        from datetime import UTC, datetime, timedelta
        from uuid import uuid4
        from ruhusa import InvocationRecord, Principal, AuthorizationRequest, TaskContext, compute_arguments_digest
        from app.main import TOOL_ID, IMPLEMENTATION_ID
        
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        # Register invocation directly with known digest
        invocation = InvocationRecord(
            invocation_id=invocation_id,
            invoking_principal_id="fastapi-gateway",
            executing_principal_id="billing-agent",
            task_id=task_id,
            action="refund",
            resource="account/recovery-not-applied-attempt2",
            arguments_digest=compute_arguments_digest({"amount": 100}),
            tool_id=TOOL_ID,
            implementation_id=IMPLEMENTATION_ID,
            recorded_at=now,
            expires_at=now + timedelta(minutes=5),
        )
        current_runtime.invocation_store.register(invocation)
        
        # Claim it
        request_claim = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource="account/recovery-not-applied-attempt2",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="claim for recovery test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        begin1 = current_runtime.controller.begin(request_claim, now=now)
        assert begin1.allowed is True
        
        initial_effects = side_effect_count()
        
        # Mark stale → UNKNOWN
        record_after_claim = current_runtime.execution_store.get(invocation_id)
        current_runtime.controller.mark_stale_claim_unknown(
            invocation_id,
            stale_after=timedelta(seconds=1),
            now=record_after_claim.claimed_at + timedelta(seconds=2),
        )
        
        # Reconcile as not applied → AVAILABLE
        current_runtime.controller.reconcile_unknown(
            invocation_id,
            outcome=ExecutionRecoveryOutcome.SIDE_EFFECT_NOT_APPLIED,
            reason="verified no backend changes",
        )
        
        # Verify state is AVAILABLE
        record = current_runtime.execution_store.get(invocation_id)
        assert record.state.value == "available"
        
        # Verify no side effect from reconciliation
        assert side_effect_count() == initial_effects
        
        # Attempt 2: fresh begin() against recovered AVAILABLE state on SAME invocation
        request_attempt2 = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource="account/recovery-not-applied-attempt2",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="attempt 2 after recovery",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        # Begin attempt 2
        begin2 = current_runtime.controller.begin(request_attempt2, now=now)
        assert begin2.allowed is True
        assert begin2.permit is not None
        assert begin2.permit.attempt == 2
        
        # Revalidate before execution
        revalidated = current_runtime.controller.revalidate_before_execution(request_attempt2, begin2.permit)
        assert revalidated.allowed is True
        
        # Simulate side effect execution before complete
        # (In the real FastAPI flow, the refund would be executed before calling complete())
        # For this test, we just verify that complete() succeeds and transitions to COMPLETED
        
        # Complete attempt 2
        completed = current_runtime.controller.complete(begin2.permit)
        assert completed is True
        
        # Verify final state
        record = current_runtime.execution_store.get(invocation_id)
        assert record.state.value == "completed"
        assert record.attempt_count == 2
        
        # Note: In real usage (via /refunds endpoint), the refund side effect would be 
        # executed after begin() but before complete(). This low-level test verifies
        # that recover y allows attempt 2 to complete successfully. The side-effect
        # counting is verified in higher-level integration tests.


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
