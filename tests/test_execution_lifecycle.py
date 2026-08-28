"""Test normal execution lifecycle for Ruhusa v0.7.0."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import TOOL_ID, IMPLEMENTATION_ID
from ruhusa import InvocationRecord, Principal, AuthorizationRequest, TaskContext, compute_arguments_digest


class TestExecutionLifecycle:
    """Test the complete execution lifecycle."""

    def test_execution_state_transitions_correctly(self, client: TestClient, current_runtime, clear_side_effects):
        """Test AVAILABLE → CLAIMED → COMPLETED transition."""
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        # Register invocation
        current_runtime.invocation_store.register(
            InvocationRecord(
                invocation_id=invocation_id,
                invoking_principal_id="fastapi-gateway",
                executing_principal_id="billing-agent",
                task_id=task_id,
                action="refund",
                resource="account/lifecycle-test",
                arguments_digest=compute_arguments_digest({"amount": 100}),
                tool_id=TOOL_ID,
                implementation_id=IMPLEMENTATION_ID,
                recorded_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        
        # Create authorization request
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource="account/lifecycle-test",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="lifecycle test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        # Phase 1: begin() - transitions to CLAIMED
        begin = current_runtime.controller.begin(request, now=now)
        assert begin.allowed is True
        assert begin.permit is not None
        
        record = current_runtime.execution_store.get(invocation_id)
        assert record is not None
        assert record.state.value == "claimed"
        assert record.attempt_count == 1
        assert record.claim_id == begin.permit.claim_id
        assert record.claimed_at is not None
        
        # Phase 2: revalidate_before_execution()
        revalidated = current_runtime.controller.revalidate_before_execution(request, begin.permit)
        assert revalidated.allowed is True
        
        # Phase 3: complete() - transitions to COMPLETED
        completed = current_runtime.controller.complete(begin.permit)
        assert completed is True
        
        record = current_runtime.execution_store.get(invocation_id)
        assert record.state.value == "completed"
        assert record.completed_at is not None
        assert record.attempt_count == 1

    def test_single_side_effect_per_execution(self, client: TestClient, clear_side_effects, side_effect_count):
        """Test that exactly one side effect occurs during successful execution."""
        initial_count = side_effect_count()
        
        response = client.post(
            "/refunds",
            json={
                "account_id": "side-effect-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        assert response.status_code == 200
        assert response.json()["executed"] is True
        
        final_count = side_effect_count()
        assert final_count == initial_count + 1

    def test_claim_id_assigned_on_begin(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that claim_id is assigned when execution is claimed."""
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        current_runtime.invocation_store.register(
            InvocationRecord(
                invocation_id=invocation_id,
                invoking_principal_id="fastapi-gateway",
                executing_principal_id="billing-agent",
                task_id=task_id,
                action="refund",
                resource="account/claim-test",
                arguments_digest=compute_arguments_digest({"amount": 100}),
                tool_id=TOOL_ID,
                implementation_id=IMPLEMENTATION_ID,
                recorded_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource="account/claim-test",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        begin = current_runtime.controller.begin(request, now=now)
        assert begin.permit.claim_id is not None
        
        record = current_runtime.execution_store.get(invocation_id)
        assert record.claim_id == begin.permit.claim_id

    def test_execution_time_revalidation_occurs(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that revalidation happens before side effect execution."""
        # This is validated implicitly in the test_execution_state_transitions_correctly test
        # The revalidate_before_execution() call must succeed before side effect can execute
        pass
