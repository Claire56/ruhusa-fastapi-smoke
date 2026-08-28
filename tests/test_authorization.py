"""Test authorization decisions for Ruhusa v0.7.0."""

import pytest
from fastapi.testclient import TestClient


class TestAuthorizationAllow:
    """Test ALLOW decision for small refunds."""

    def test_small_refund_allows_execution(self, client: TestClient, clear_side_effects):
        """Test that billing agent can execute small refunds ($100)."""
        response = client.post(
            "/refunds",
            json={
                "account_id": "authorization-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        assert response.status_code == 200
        body = response.json()
        assert body["executed"] is True
        assert body["effect"] == "allow"
        assert body["execution_state"] == "completed"
        assert body["refund"] is not None
        assert body["refund"]["amount"] == 100


class TestAuthorizationRequireApproval:
    """Test REQUIRE_APPROVAL decision for large refunds."""

    def test_large_refund_requires_approval(self, client: TestClient, clear_side_effects):
        """Test that refunds > $500 require approval."""
        response = client.post(
            "/refunds",
            json={
                "account_id": "large-refund-test",
                "amount": 600,
                "principal_id": "billing-agent",
            },
        )
        
        assert response.status_code == 202
        body = response.json()
        assert body["executed"] is False
        assert body["effect"] == "require_approval"
        
        # Verify no side effect occurred
        response = client.get("/refunds")
        assert response.status_code == 200
        refunds = response.json()
        assert refunds["count"] == 0

    def test_refund_at_boundary(self, client: TestClient, clear_side_effects):
        """Test refund at exactly $500 boundary (should ALLOW)."""
        response = client.post(
            "/refunds",
            json={
                "account_id": "boundary-test",
                "amount": 500.0,
                "principal_id": "billing-agent",
            },
        )
        
        assert response.status_code == 200
        body = response.json()
        assert body["executed"] is True
        assert body["effect"] == "allow"


class TestAuthorizationDeny:
    """Test DEFAULT DENY for unknown principals."""

    def test_unknown_principal_denied(self, client: TestClient, clear_side_effects):
        """Test that unknown principals are denied."""
        response = client.post(
            "/refunds",
            json={
                "account_id": "deny-test",
                "amount": 100,
                "principal_id": "rogue-agent",
            },
        )
        
        assert response.status_code == 403
        body = response.json()
        assert body["executed"] is False
        assert body["effect"] == "deny"
        
        # Verify no side effect occurred
        response = client.get("/refunds")
        assert response.status_code == 200
        refunds = response.json()
        assert refunds["count"] == 0

    def test_wrong_principal_type_denied(self, client: TestClient, clear_side_effects):
        """Test that principals not in policy are denied."""
        response = client.post(
            "/refunds",
            json={
                "account_id": "wrong-principal",
                "amount": 100,
                "principal_id": "unauthorized-agent",
            },
        )
        
        assert response.status_code == 403
        body = response.json()
        assert body["executed"] is False
        assert body["effect"] == "deny"


class TestAuthorizationExpiration:
    """Test task and invocation expiration."""

    def test_audit_events_created_for_decisions(self, client: TestClient, clear_side_effects):
        """Test that all authorization decisions create audit events."""
        # ALLOW
        client.post(
            "/refunds",
            json={
                "account_id": "audit-allow",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        # REQUIRE_APPROVAL
        client.post(
            "/refunds",
            json={
                "account_id": "audit-approval",
                "amount": 600,
                "principal_id": "billing-agent",
            },
        )
        
        # DENY
        client.post(
            "/refunds",
            json={
                "account_id": "audit-deny",
                "amount": 100,
                "principal_id": "rogue-agent",
            },
        )
        
        response = client.get("/audit")
        assert response.status_code == 200
        audit = response.json()
        assert audit["count"] >= 3
        assert audit["chain_valid"] is True
