"""Test invocation integrity and provenance for Ruhusa v0.7.0."""

import pytest
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import TOOL_ID, IMPLEMENTATION_ID
from ruhusa import InvocationRecord, Principal, AuthorizationRequest, TaskContext, compute_arguments_digest


class TestProvenanceIntegrity:
    """Test canonical invocation integrity and provenance validation."""

    def test_valid_invocation_allows_execution(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that a valid canonical invocation allows execution."""
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        # Register canonical invocation
        current_runtime.invocation_store.register(
            InvocationRecord(
                invocation_id=invocation_id,
                invoking_principal_id="fastapi-gateway",
                executing_principal_id="billing-agent",
                task_id=task_id,
                action="refund",
                resource="account/provenance-test",
                arguments_digest=compute_arguments_digest({"amount": 100}),
                tool_id=TOOL_ID,
                implementation_id=IMPLEMENTATION_ID,
                recorded_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        
        # Execute with matching invocation
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource="account/provenance-test",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="provenance test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        begin = current_runtime.controller.begin(request, now=now)
        assert begin.allowed is True
        assert begin.permit is not None

    def test_principal_mismatch_denied(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that principal mismatch in execution request is denied."""
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        # Register canonical invocation for billing-agent
        current_runtime.invocation_store.register(
            InvocationRecord(
                invocation_id=invocation_id,
                invoking_principal_id="fastapi-gateway",
                executing_principal_id="billing-agent",
                task_id=task_id,
                action="refund",
                resource="account/principal-mismatch",
                arguments_digest=compute_arguments_digest({"amount": 100}),
                tool_id=TOOL_ID,
                implementation_id=IMPLEMENTATION_ID,
                recorded_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        
        # Try to execute as different principal
        request = AuthorizationRequest(
            principal=Principal(principal_id="other-agent", principal_type="agent"),
            action="refund",
            resource="account/principal-mismatch",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        decision = current_runtime.authorizer.authorize(request, now=now)
        assert decision.allowed is False
        
        # Verify no side effect
        response = client.get("/refunds")
        assert response.json()["count"] == 0

    def test_action_mismatch_denied(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that action mismatch is denied."""
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        # Register for "refund" action
        current_runtime.invocation_store.register(
            InvocationRecord(
                invocation_id=invocation_id,
                invoking_principal_id="fastapi-gateway",
                executing_principal_id="billing-agent",
                task_id=task_id,
                action="refund",
                resource="account/action-mismatch",
                arguments_digest=compute_arguments_digest({"amount": 100}),
                tool_id=TOOL_ID,
                implementation_id=IMPLEMENTATION_ID,
                recorded_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        
        # Try to execute with different action
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="charge",  # Different action
            resource="account/action-mismatch",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        decision = current_runtime.authorizer.authorize(request, now=now)
        assert decision.allowed is False

    def test_resource_mismatch_denied(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that resource mismatch is denied."""
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        # Register for account/alice
        current_runtime.invocation_store.register(
            InvocationRecord(
                invocation_id=invocation_id,
                invoking_principal_id="fastapi-gateway",
                executing_principal_id="billing-agent",
                task_id=task_id,
                action="refund",
                resource="account/alice",
                arguments_digest=compute_arguments_digest({"amount": 100}),
                tool_id=TOOL_ID,
                implementation_id=IMPLEMENTATION_ID,
                recorded_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        
        # Try to execute on account/bob
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource="account/bob",  # Different resource
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        decision = current_runtime.authorizer.authorize(request, now=now)
        assert decision.allowed is False

    def test_arguments_digest_mismatch_denied(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that arguments digest mismatch is denied."""
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        # Register with amount=100
        current_runtime.invocation_store.register(
            InvocationRecord(
                invocation_id=invocation_id,
                invoking_principal_id="fastapi-gateway",
                executing_principal_id="billing-agent",
                task_id=task_id,
                action="refund",
                resource="account/digest-mismatch",
                arguments_digest=compute_arguments_digest({"amount": 100}),
                tool_id=TOOL_ID,
                implementation_id=IMPLEMENTATION_ID,
                recorded_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        
        # Try to execute with amount=200
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource="account/digest-mismatch",
            arguments={"amount": 200},  # Different amount
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        decision = current_runtime.authorizer.authorize(request, now=now)
        assert decision.allowed is False

    def test_unknown_invocation_denied(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that referencing an unknown invocation ID is denied."""
        now = datetime.now(UTC)
        
        # Reference a non-existent invocation
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource="account/unknown",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=f"task-{uuid4().hex}",
                initiated_by="test",
                purpose="test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id="inv-nonexistent",
        )
        
        decision = current_runtime.authorizer.authorize(request, now=now)
        assert decision.allowed is False

    def test_untrusted_tool_id_denied(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that untrusted tool IDs are denied."""
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        # Register with untrusted tool ID
        current_runtime.invocation_store.register(
            InvocationRecord(
                invocation_id=invocation_id,
                invoking_principal_id="fastapi-gateway",
                executing_principal_id="billing-agent",
                task_id=task_id,
                action="refund",
                resource="account/untrusted-tool",
                arguments_digest=compute_arguments_digest({"amount": 100}),
                tool_id="unknown-tool",  # Not registered
                implementation_id="unknown-tool@sha256:v1",
                recorded_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource="account/untrusted-tool",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        decision = current_runtime.authorizer.authorize(request, now=now)
        assert decision.allowed is False

    def test_incorrect_implementation_id_denied(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that mismatched implementation IDs are denied."""
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        from app.main import TOOL_ID
        
        # Register with different implementation ID
        current_runtime.invocation_store.register(
            InvocationRecord(
                invocation_id=invocation_id,
                invoking_principal_id="fastapi-gateway",
                executing_principal_id="billing-agent",
                task_id=task_id,
                action="refund",
                resource="account/wrong-impl",
                arguments_digest=compute_arguments_digest({"amount": 100}),
                tool_id=TOOL_ID,
                implementation_id="refund-tool@sha256:wrong-version",  # Different from registered
                recorded_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="refund",
            resource="account/wrong-impl",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        decision = current_runtime.authorizer.authorize(request, now=now)
        assert decision.allowed is False

    def test_tool_not_authorized_for_action_denied(self, client: TestClient, current_runtime, clear_side_effects):
        """Test that tools not authorized for requested action are denied."""
        now = datetime.now(UTC)
        invocation_id = f"inv-{uuid4().hex}"
        task_id = f"task-{uuid4().hex}"
        
        from app.main import TOOL_ID, IMPLEMENTATION_ID
        
        # Register invocation for action not in tool's allowed_actions
        current_runtime.invocation_store.register(
            InvocationRecord(
                invocation_id=invocation_id,
                invoking_principal_id="fastapi-gateway",
                executing_principal_id="billing-agent",
                task_id=task_id,
                action="charge",  # Tool only allows "refund"
                resource="account/wrong-action",
                arguments_digest=compute_arguments_digest({"amount": 100}),
                tool_id=TOOL_ID,
                implementation_id=IMPLEMENTATION_ID,
                recorded_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        
        request = AuthorizationRequest(
            principal=Principal(principal_id="billing-agent", principal_type="agent"),
            action="charge",  # Not in refund-tool's allowed_actions
            resource="account/wrong-action",
            arguments={"amount": 100},
            task=TaskContext(
                task_id=task_id,
                initiated_by="test",
                purpose="test",
                expires_at=now + timedelta(minutes=5),
            ),
            invocation_id=invocation_id,
        )
        
        decision = current_runtime.authorizer.authorize(request, now=now)
        assert decision.allowed is False
