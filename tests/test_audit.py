"""Test audit logging and fail-closed behavior for Ruhusa v0.7.0."""

import pytest
from fastapi.testclient import TestClient


class TestAuditLogging:
    """Test audit event creation and chain integrity."""

    def test_allow_creates_audit_event(self, client: TestClient, clear_side_effects):
        """Test that ALLOW decision creates an audit event."""
        response = client.post(
            "/refunds",
            json={
                "account_id": "audit-allow",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        assert response.status_code == 200
        
        audit_response = client.get("/audit")
        assert audit_response.status_code == 200
        audit = audit_response.json()
        assert audit["count"] >= 1
        assert audit["chain_valid"] is True

    def test_require_approval_creates_audit_event(self, client: TestClient, clear_side_effects):
        """Test that REQUIRE_APPROVAL decision creates an audit event."""
        response = client.post(
            "/refunds",
            json={
                "account_id": "audit-approval",
                "amount": 600,
                "principal_id": "billing-agent",
            },
        )
        
        assert response.status_code == 202
        
        audit_response = client.get("/audit")
        assert audit_response.status_code == 200
        audit = audit_response.json()
        assert audit["count"] >= 1
        assert audit["chain_valid"] is True

    def test_deny_creates_audit_event(self, client: TestClient, clear_side_effects):
        """Test that DENY decision creates an audit event."""
        response = client.post(
            "/refunds",
            json={
                "account_id": "audit-deny",
                "amount": 100,
                "principal_id": "rogue-agent",
            },
        )
        
        assert response.status_code == 403
        
        audit_response = client.get("/audit")
        assert audit_response.status_code == 200
        audit = audit_response.json()
        assert audit["count"] >= 1
        assert audit["chain_valid"] is True

    def test_audit_chain_links_correctly(self, client: TestClient, clear_side_effects):
        """Test that audit events link correctly via previous_hash."""
        # Create several refunds to generate audit events
        for i in range(3):
            client.post(
                "/refunds",
                json={
                    "account_id": f"audit-chain-{i}",
                    "amount": 100,
                    "principal_id": "billing-agent",
                },
            )
        
        audit_response = client.get("/audit")
        assert audit_response.status_code == 200
        audit = audit_response.json()
        
        # Verify chain integrity
        assert audit["chain_valid"] is True
        assert audit["count"] >= 3


class TestAuditFailClosed:
    """Test that authorization defaults to DENY when audit is unavailable."""

    def test_audit_failure_denies_operation(self, client: TestClient, clear_side_effects, side_effect_count):
        """Test that audit failure causes DENY (fail-closed)."""
        initial_effects = side_effect_count()
        
        response = client.post("/failure/audit")
        
        assert response.status_code == 200
        body = response.json()
        
        # Policy would ALLOW, but audit failure causes DENY
        assert body["policy_would_allow"] is True
        assert body["final_effect"] == "deny"
        assert body["allowed"] is False
        
        # Verify no side effect
        final_effects = side_effect_count()
        assert final_effects == initial_effects
