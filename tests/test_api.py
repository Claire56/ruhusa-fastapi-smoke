from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # Backend can be either memory or postgres depending on DSN
    assert body["ruhusa_backend"] in ("memory", "postgres")
    assert body["audit_chain_valid"] is True


def test_small_refund_executes() -> None:
    response = client.post(
        "/refunds",
        json={"account_id": "acct-123", "amount": 100, "principal_id": "billing-agent"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["executed"] is True
    assert body["effect"] == "allow"
    assert body["execution_state"] == "completed"


def test_large_refund_requires_approval() -> None:
    response = client.post(
        "/refunds",
        json={"account_id": "acct-456", "amount": 900, "principal_id": "billing-agent"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["executed"] is False
    assert body["effect"] == "require_approval"


def test_unknown_principal_is_denied() -> None:
    response = client.post(
        "/refunds",
        json={"account_id": "acct-789", "amount": 100, "principal_id": "rogue-agent"},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["executed"] is False
    assert body["effect"] == "deny"


def test_audit_chain_remains_valid() -> None:
    client.post(
        "/refunds",
        json={"account_id": "acct-audit", "amount": 50, "principal_id": "billing-agent"},
    )
    response = client.get("/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert body["chain_valid"] is True
