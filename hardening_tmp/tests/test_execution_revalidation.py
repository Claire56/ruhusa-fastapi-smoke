"""Execution-time revalidation tests.

These tests verify a real time-of-check/time-of-use change: authority is valid
when execution is claimed, but the task expires before the protected side
effect is allowed to run.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.main import IMPLEMENTATION_ID, TOOL_ID
from ruhusa import (
    AuthorizationRequest,
    InvocationRecord,
    Principal,
    TaskContext,
    compute_arguments_digest,
)


def test_task_expiry_between_begin_and_execution_cancels_claim(
    current_runtime,
    clear_side_effects,
    side_effect_count,
):
    now = datetime.now(UTC)
    invocation_id = f"inv-{uuid4().hex}"
    task_id = f"task-{uuid4().hex}"
    arguments = {"amount": 100}
    resource = "account/revalidation-expiry"

    current_runtime.invocation_store.register(
        InvocationRecord(
            invocation_id=invocation_id,
            invoking_principal_id="fastapi-gateway",
            executing_principal_id="billing-agent",
            task_id=task_id,
            action="refund",
            resource=resource,
            arguments_digest=compute_arguments_digest(arguments),
            tool_id=TOOL_ID,
            implementation_id=IMPLEMENTATION_ID,
            recorded_at=now,
            expires_at=now + timedelta(minutes=10),
        )
    )

    request = AuthorizationRequest(
        principal=Principal(
            principal_id="billing-agent",
            principal_type="agent",
        ),
        action="refund",
        resource=resource,
        arguments=arguments,
        task=TaskContext(
            task_id=task_id,
            initiated_by="validation-suite",
            purpose="execution-time task expiry",
            expires_at=now + timedelta(seconds=1),
        ),
        invocation_id=invocation_id,
    )

    before_effects = side_effect_count()

    begin = current_runtime.controller.begin(request, now=now)
    assert begin.allowed is True
    assert begin.permit is not None

    claimed = current_runtime.execution_store.get(invocation_id)
    assert claimed is not None
    assert claimed.state.value == "claimed"
    assert claimed.attempt_count == 1

    revalidated = current_runtime.controller.revalidate_before_execution(
        request,
        begin.permit,
        now=now + timedelta(seconds=2),
    )

    assert revalidated.allowed is False
    assert "task expired" in revalidated.reason

    cancelled = current_runtime.execution_store.get(invocation_id)
    assert cancelled is not None
    assert cancelled.state.value == "cancelled"
    assert cancelled.attempt_count == 1

    assert current_runtime.controller.complete(begin.permit) is False
    assert side_effect_count() == before_effects
