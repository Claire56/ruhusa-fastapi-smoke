from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ruhusa import (
    AuthorizationRequest,
    DecisionEffect,
    ExecutionController,
    ExecutionRecoveryOutcome,
    InMemoryAuditLog,
    InMemoryExecutionStore,
    InMemoryInvocationStore,
    InMemoryRevocationStore,
    InMemoryToolRegistry,
    InvocationRecord,
    PolicyRule,
    Principal,
    Ruhusa,
    StaticPolicyStore,
    TaskContext,
    ToolRegistration,
    compute_arguments_digest,
)

TOOL_ID = "refund-tool"
IMPLEMENTATION_ID = "refund-tool@sha256:demo-v1"


class RefundInput(BaseModel):
    account_id: str = Field(min_length=1)
    amount: float = Field(gt=0)
    principal_id: str = "billing-agent"

class ReplayInput(BaseModel):
    account_id: str = Field(min_length=1)
    amount: float = Field(gt=0)
    principal_id: str = "billing-agent"

class RecoveryInput(BaseModel):
    outcome: str
    reason: str = Field(min_length=1)

@dataclass
class Runtime:
    backend: str
    authorizer: Ruhusa
    controller: ExecutionController
    invocation_store: Any
    tool_registry: Any
    audit_log: Any
    execution_store: Any
    pool: Any = None


def _small_refund(request: AuthorizationRequest) -> bool:
    amount = request.arguments.get("amount")
    return isinstance(amount, (int, float)) and float(amount) <= 500.0


def _policy_store() -> StaticPolicyStore:
    return StaticPolicyStore(
        [
            PolicyRule(
                policy_id="refund-small",
                effect=DecisionEffect.ALLOW,
                actions=frozenset({"refund"}),
                principal_ids=frozenset({"billing-agent"}),
                resource_prefixes=("account/",),
                condition=_small_refund,
                reason="billing agent may issue refunds up to 500",
            ),
            PolicyRule(
                policy_id="refund-large-approval",
                effect=DecisionEffect.REQUIRE_APPROVAL,
                actions=frozenset({"refund"}),
                principal_ids=frozenset({"billing-agent"}),
                resource_prefixes=("account/",),
                reason="refunds above 500 require human approval",
                obligations=("human_approval",),
            ),
        ]
    )


def _register_tool(tool_registry: Any) -> None:
    if tool_registry.is_trusted(TOOL_ID, IMPLEMENTATION_ID):
        return
    tool_registry.register(
        ToolRegistration(
            tool_id=TOOL_ID,
            implementation_id=IMPLEMENTATION_ID,
            allowed_actions=frozenset({"refund"}),
        )
    )


def build_runtime() -> Runtime:
    dsn = os.getenv("RUHUSA_POSTGRES_DSN")

    if dsn:
        from ruhusa.postgres import (
            PostgresAuditLog,
            PostgresExecutionStore,
            PostgresInvocationStore,
            PostgresRevocationStore,
            PostgresToolRegistry,
            create_postgres_pool,
            initialize_postgres_schema,
        )

        pool = create_postgres_pool(dsn, min_size=1, max_size=10)
        initialize_postgres_schema(pool)
        audit_log = PostgresAuditLog(pool)
        invocation_store = PostgresInvocationStore(pool)
        tool_registry = PostgresToolRegistry(pool)
        execution_store = PostgresExecutionStore(pool)
        revocation_store = PostgresRevocationStore(pool)
        backend = "postgres"
    else:
        pool = None
        audit_log = InMemoryAuditLog()
        invocation_store = InMemoryInvocationStore()
        tool_registry = InMemoryToolRegistry()
        execution_store = InMemoryExecutionStore()
        revocation_store = InMemoryRevocationStore()
        backend = "memory"

    _register_tool(tool_registry)

    authorizer = Ruhusa(
        policy_store=_policy_store(),
        audit_log=audit_log,
        revocation_store=revocation_store,
        invocation_store=invocation_store,
        tool_registry=tool_registry,
    )
    controller = ExecutionController(
        authorizer=authorizer,
        execution_store=execution_store,
    )

    return Runtime(
        backend=backend,
        authorizer=authorizer,
        controller=controller,
        invocation_store=invocation_store,
        tool_registry=tool_registry,
        audit_log=audit_log,
        execution_store=execution_store,
        pool=pool,
    )


runtime = build_runtime()
app = FastAPI(title="Ruhusa v0.7.0 FastAPI Smoke Test", version="0.1.0")
refund_side_effects: list[dict[str, Any]] = []


def _audit_events() -> tuple[Any, ...]:
    snapshot = getattr(runtime.audit_log, "snapshot", None)
    if callable(snapshot):
        return tuple(snapshot())
    return tuple(runtime.audit_log.events)


def _audit_chain_valid() -> bool:
    return bool(runtime.audit_log.verify_chain())


@app.on_event("shutdown")
def close_runtime() -> None:
    if runtime.pool is not None:
        runtime.pool.close()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "ruhusa_backend": runtime.backend,
        "audit_chain_valid": _audit_chain_valid(),
    }


@app.post("/refunds")
def create_refund(payload: RefundInput):
    now = datetime.now(UTC)
    task_id = f"task-{uuid4().hex}"
    invocation_id = f"inv-{uuid4().hex}"
    resource = f"account/{payload.account_id}"
    arguments = {"amount": payload.amount}

    runtime.invocation_store.register(
        InvocationRecord(
            invocation_id=invocation_id,
            invoking_principal_id="fastapi-gateway",
            executing_principal_id=payload.principal_id,
            task_id=task_id,
            action="refund",
            resource=resource,
            arguments_digest=compute_arguments_digest(arguments),
            tool_id=TOOL_ID,
            implementation_id=IMPLEMENTATION_ID,
            recorded_at=now,
            expires_at=now + timedelta(minutes=5),
        )
    )

    request = AuthorizationRequest(
        principal=Principal(principal_id=payload.principal_id, principal_type="agent"),
        action="refund",
        resource=resource,
        arguments=arguments,
        task=TaskContext(
            task_id=task_id,
            initiated_by="demo-user",
            purpose="refund smoke test",
            expires_at=now + timedelta(minutes=10),
        ),
        invocation_id=invocation_id,
    )

    begin = runtime.controller.begin(request, now=now)

    if not begin.allowed or begin.permit is None:
        status_code = (
            202
            if begin.authorization.effect is DecisionEffect.REQUIRE_APPROVAL
            else 403
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "executed": False,
                "effect": begin.authorization.effect.value,
                "reason": begin.reason,
                "audit_id": begin.authorization.audit_id,
                "invocation_id": invocation_id,
            },
        )

    revalidated = runtime.controller.revalidate_before_execution(
        request,
        begin.permit,
    )
    if not revalidated.allowed:
        return JSONResponse(
            status_code=403,
            content={
                "executed": False,
                "effect": revalidated.authorization.effect.value,
                "reason": revalidated.reason,
                "audit_id": revalidated.authorization.audit_id,
                "invocation_id": invocation_id,
            },
        )

    side_effect = {
        "refund_id": f"refund-{uuid4().hex}",
        "account_id": payload.account_id,
        "amount": payload.amount,
        "executed_by": payload.principal_id,
        "invocation_id": invocation_id,
    }
    refund_side_effects.append(side_effect)

    completed = runtime.controller.complete(begin.permit)
    if not completed:
        return JSONResponse(
            status_code=500,
            content={
                "executed": True,
                "completion_recorded": False,
                "warning": "side effect succeeded but completion was not recorded",
                "invocation_id": invocation_id,
                "refund": side_effect,
            },
        )

    record = runtime.execution_store.get(invocation_id)

    return {
        "executed": True,
        "effect": revalidated.authorization.effect.value,
        "reason": revalidated.reason,
        "audit_id": revalidated.authorization.audit_id,
        "invocation_id": invocation_id,
        "execution_state": record.state.value if record else None,
        "refund": side_effect,
    }


@app.get("/refunds")
def list_refunds() -> dict[str, Any]:
    return {"count": len(refund_side_effects), "items": refund_side_effects}


@app.get("/audit")
def list_audit_events() -> dict[str, Any]:
    events = _audit_events()
    return {
        "count": len(events),
        "chain_valid": _audit_chain_valid(),
        "events": [asdict(event) for event in events],
    }
    
    
@app.get("/executions/{invocation_id}")
def get_execution(invocation_id: str):
    record = runtime.execution_store.get(invocation_id)

    if record is None:
        return JSONResponse(
            status_code=404,
            content={
                "found": False,
                "invocation_id": invocation_id,
            },
        )

    return {
        "found": True,
        "invocation_id": record.invocation_id,
        "state": record.state.value,
        "attempt_count": record.attempt_count,
        "claim_id": record.claim_id,
        "claimed_at": (
            record.claimed_at.isoformat()
            if record.claimed_at
            else None
        ),
        "completed_at": (
            record.completed_at.isoformat()
            if record.completed_at
            else None
        ),
        "recovery_count": record.recovery_count,
    }

@app.post("/replay/{invocation_id}")
def replay_invocation(invocation_id: str, payload: ReplayInput):
    canonical = runtime.invocation_store.get(invocation_id)

    if canonical is None:
        return JSONResponse(
            status_code=404,
            content={
                "found": False,
                "invocation_id": invocation_id,
            },
        )

    before = runtime.execution_store.get(invocation_id)

    arguments = {"amount": payload.amount}

    request = AuthorizationRequest(
        principal=Principal(
            principal_id=payload.principal_id,
            principal_type="agent",
        ),
        action="refund",
        resource=f"account/{payload.account_id}",
        arguments=arguments,
        task=TaskContext(
            task_id=canonical.task_id,
            initiated_by="replay-test",
            purpose="replay protection smoke test",
            expires_at=canonical.expires_at,
        ),
        invocation_id=invocation_id,
    )

    result = runtime.controller.begin(
        request,
        now=datetime.now(UTC),
    )

    after = runtime.execution_store.get(invocation_id)

    content = {
        "invocation_id": invocation_id,
        "replay_blocked": not result.allowed,
        "authorization_effect": result.authorization.effect.value,
        "execution_allowed": result.allowed,
        "permit_issued": result.permit is not None,
        "reason": result.reason,
        "state_before": before.state.value if before else None,
        "state_after": after.state.value if after else None,
        "attempt_count_before": before.attempt_count if before else None,
        "attempt_count_after": after.attempt_count if after else None,
    }

    return JSONResponse(
        status_code=409 if not result.allowed else 200,
        content=content,
    )
    
@app.post("/concurrency/prepare")
def prepare_concurrency_test(payload: RefundInput):
    now = datetime.now(UTC)

    task_id = f"task-{uuid4().hex}"
    invocation_id = f"inv-{uuid4().hex}"
    resource = f"account/{payload.account_id}"
    arguments = {"amount": payload.amount}
    expires_at = now + timedelta(minutes=5)

    runtime.invocation_store.register(
        InvocationRecord(
            invocation_id=invocation_id,
            invoking_principal_id="fastapi-gateway",
            executing_principal_id=payload.principal_id,
            task_id=task_id,
            action="refund",
            resource=resource,
            arguments_digest=compute_arguments_digest(arguments),
            tool_id=TOOL_ID,
            implementation_id=IMPLEMENTATION_ID,
            recorded_at=now,
            expires_at=expires_at,
        )
    )

    return {
        "invocation_id": invocation_id,
        "task_id": task_id,
        "account_id": payload.account_id,
        "amount": payload.amount,
        "principal_id": payload.principal_id,
        "expires_at": expires_at.isoformat(),
    }    
    
    
@app.post("/concurrency/{invocation_id}")
def concurrency_execute(invocation_id: str, payload: RefundInput):
    canonical = runtime.invocation_store.get(invocation_id)

    if canonical is None:
        return JSONResponse(
            status_code=404,
            content={
                "invocation_id": invocation_id,
                "executed": False,
                "reason": "canonical invocation not found",
            },
        )

    now = datetime.now(UTC)

    request = AuthorizationRequest(
        principal=Principal(
            principal_id=payload.principal_id,
            principal_type="agent",
        ),
        action="refund",
        resource=f"account/{payload.account_id}",
        arguments={"amount": payload.amount},
        task=TaskContext(
            task_id=canonical.task_id,
            initiated_by="concurrency-test",
            purpose="single-winner concurrency smoke test",
            expires_at=canonical.expires_at,
        ),
        invocation_id=invocation_id,
    )

    begin = runtime.controller.begin(request, now=now)

    if not begin.allowed or begin.permit is None:
        record = runtime.execution_store.get(invocation_id)

        return JSONResponse(
            status_code=409,
            content={
                "invocation_id": invocation_id,
                "executed": False,
                "winner": False,
                "permit_issued": False,
                "reason": begin.reason,
                "state": record.state.value if record else None,
                "attempt_count": record.attempt_count if record else None,
            },
        )

    revalidated = runtime.controller.revalidate_before_execution(
        request,
        begin.permit,
    )

    if not revalidated.allowed:
        return JSONResponse(
            status_code=403,
            content={
                "invocation_id": invocation_id,
                "executed": False,
                "winner": False,
                "reason": revalidated.reason,
            },
        )

    side_effect = {
        "refund_id": f"refund-{uuid4().hex}",
        "account_id": payload.account_id,
        "amount": payload.amount,
        "invocation_id": invocation_id,
        "claim_id": begin.permit.claim_id,
    }

    refund_side_effects.append(side_effect)

    completed = runtime.controller.complete(begin.permit)

    record = runtime.execution_store.get(invocation_id)

    return {
        "invocation_id": invocation_id,
        "executed": True,
        "winner": True,
        "permit_issued": True,
        "claim_id": begin.permit.claim_id,
        "attempt": begin.permit.attempt,
        "completion_recorded": completed,
        "state": record.state.value if record else None,
        "attempt_count": record.attempt_count if record else None,
        "refund": side_effect,
    }
    
@app.post("/failure/audit")
def audit_failure_test():
    class FailingAuditLog:
        def append(self, request, decision):
            raise RuntimeError("simulated audit backend outage")

        def verify_chain(self):
            return False

    now = datetime.now(UTC)

    invocation_store = InMemoryInvocationStore()
    tool_registry = InMemoryToolRegistry()

    tool_registry.register(
        ToolRegistration(
            tool_id=TOOL_ID,
            implementation_id=IMPLEMENTATION_ID,
            allowed_actions=frozenset({"refund"}),
        )
    )

    invocation_id = f"inv-{uuid4().hex}"
    task_id = f"task-{uuid4().hex}"

    arguments = {"amount": 100.0}

    invocation_store.register(
        InvocationRecord(
            invocation_id=invocation_id,
            invoking_principal_id="fastapi-gateway",
            executing_principal_id="billing-agent",
            task_id=task_id,
            action="refund",
            resource="account/audit-failure",
            arguments_digest=compute_arguments_digest(arguments),
            tool_id=TOOL_ID,
            implementation_id=IMPLEMENTATION_ID,
            recorded_at=now,
            expires_at=now + timedelta(minutes=5),
        )
    )

    authorizer = Ruhusa(
        policy_store=_policy_store(),
        audit_log=FailingAuditLog(),
        revocation_store=InMemoryRevocationStore(),
        invocation_store=invocation_store,
        tool_registry=tool_registry,
    )

    request = AuthorizationRequest(
        principal=Principal(
            principal_id="billing-agent",
            principal_type="agent",
        ),
        action="refund",
        resource="account/audit-failure",
        arguments=arguments,
        task=TaskContext(
            task_id=task_id,
            initiated_by="demo-user",
            purpose="audit fail-closed smoke test",
            expires_at=now + timedelta(minutes=10),
        ),
        invocation_id=invocation_id,
    )

    decision = authorizer.authorize(request, now=now)

    return {
        "policy_would_allow": True,
        "final_effect": decision.effect.value,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "side_effect_executed": False,
    }
    
@app.post("/failure/claim-only")
def create_abandoned_claim(payload: RefundInput):
    now = datetime.now(UTC)

    task_id = f"task-{uuid4().hex}"
    invocation_id = f"inv-{uuid4().hex}"
    resource = f"account/{payload.account_id}"
    arguments = {"amount": payload.amount}

    expires_at = now + timedelta(minutes=5)

    runtime.invocation_store.register(
        InvocationRecord(
            invocation_id=invocation_id,
            invoking_principal_id="fastapi-gateway",
            executing_principal_id=payload.principal_id,
            task_id=task_id,
            action="refund",
            resource=resource,
            arguments_digest=compute_arguments_digest(arguments),
            tool_id=TOOL_ID,
            implementation_id=IMPLEMENTATION_ID,
            recorded_at=now,
            expires_at=expires_at,
        )
    )

    request = AuthorizationRequest(
        principal=Principal(
            principal_id=payload.principal_id,
            principal_type="agent",
        ),
        action="refund",
        resource=resource,
        arguments=arguments,
        task=TaskContext(
            task_id=task_id,
            initiated_by="failure-test",
            purpose="abandoned execution test",
            expires_at=expires_at,
        ),
        invocation_id=invocation_id,
    )

    result = runtime.controller.begin(request, now=now)

    record = runtime.execution_store.get(invocation_id)

    return {
        "invocation_id": invocation_id,
        "claimed": result.allowed,
        "permit_issued": result.permit is not None,
        "state": record.state.value if record else None,
        "attempt_count": record.attempt_count if record else None,
        "claim_id": record.claim_id if record else None,
        "side_effect_executed": False,
    }
    
    
@app.post("/failure/stale/{invocation_id}")
def mark_claim_stale(invocation_id: str):
    record = runtime.execution_store.get(invocation_id)

    if record is None:
        return JSONResponse(
            status_code=404,
            content={"found": False},
        )

    if record.claimed_at is None:
        return JSONResponse(
            status_code=409,
            content={
                "found": True,
                "reason": "execution has no active claim",
            },
        )

    changed = runtime.controller.mark_stale_claim_unknown(
        invocation_id,
        stale_after=timedelta(seconds=1),
        now=record.claimed_at + timedelta(seconds=2),
    )

    updated = runtime.execution_store.get(invocation_id)

    return {
        "changed": changed,
        "invocation_id": invocation_id,
        "state": updated.state.value if updated else None,
        "attempt_count": updated.attempt_count if updated else None,
        "claim_id": updated.claim_id if updated else None,
    }