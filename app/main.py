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
