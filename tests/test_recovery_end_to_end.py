"""End-to-end recovery validation using the smoke application's protected side effect."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _assert_same_invocation_attempt_two(
    client: TestClient,
    side_effect_count,
) -> None:
    account_id = "recovery-attempt-two"

    claim = client.post(
        "/failure/claim-only",
        json={
            "account_id": account_id,
            "amount": 100,
            "principal_id": "billing-agent",
        },
    )
    assert claim.status_code == 200
    claim_body = claim.json()
    assert claim_body["state"] == "claimed"
    assert claim_body["attempt_count"] == 1
    invocation_id = claim_body["invocation_id"]

    stale = client.post(f"/failure/stale/{invocation_id}")
    assert stale.status_code == 200
    assert stale.json()["state"] == "unknown"

    blocked_before = side_effect_count()

    replay_while_unknown = client.post(
        f"/replay/{invocation_id}",
        json={
            "account_id": account_id,
            "amount": 100,
            "principal_id": "billing-agent",
        },
    )
    assert replay_while_unknown.status_code == 409
    assert replay_while_unknown.json()["execution_allowed"] is False
    assert replay_while_unknown.json()["state_after"] == "unknown"
    assert side_effect_count() == blocked_before

    reconcile = client.post(
        f"/failure/reconcile/{invocation_id}",
        json={
            "outcome": "side_effect_not_applied",
            "reason": "external provider confirms no refund was applied",
        },
    )
    assert reconcile.status_code == 200
    reconcile_body = reconcile.json()
    assert reconcile_body["reconciled"] is True
    assert reconcile_body["state_before"] == "unknown"
    assert reconcile_body["state_after"] == "available"
    assert reconcile_body["attempt_count"] == 1
    assert reconcile_body["recovery_count"] == 1

    execute = client.post(
        f"/concurrency/{invocation_id}",
        json={
            "account_id": account_id,
            "amount": 100,
            "principal_id": "billing-agent",
        },
    )
    assert execute.status_code == 200
    execute_body = execute.json()
    assert execute_body["executed"] is True
    assert execute_body["winner"] is True
    assert execute_body["permit_issued"] is True
    assert execute_body["attempt"] == 2
    assert execute_body["attempt_count"] == 2
    assert execute_body["state"] == "completed"

    assert side_effect_count() == blocked_before + 1

    final_record = client.get(f"/executions/{invocation_id}")
    assert final_record.status_code == 200
    final_body = final_record.json()
    assert final_body["state"] == "completed"
    assert final_body["attempt_count"] == 2
    assert final_body["recovery_count"] == 1


def test_recovered_same_invocation_executes_exactly_once_on_attempt_two(
    client: TestClient,
    clear_side_effects,
    side_effect_count,
):
    _assert_same_invocation_attempt_two(client, side_effect_count)


@pytest.mark.postgres
def test_postgres_recovered_same_invocation_executes_exactly_once_on_attempt_two(
    client: TestClient,
    current_runtime,
    clear_side_effects,
    side_effect_count,
):
    assert current_runtime.backend == "postgres"
    _assert_same_invocation_attempt_two(client, side_effect_count)
