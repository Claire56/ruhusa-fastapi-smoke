"""Test replay protection for Ruhusa v0.7.0."""

import pytest
from fastapi.testclient import TestClient


class TestReplayProtection:
    """Test that completed invocations cannot be replayed."""

    def test_replay_blocked_after_completion(self, client: TestClient, clear_side_effects, side_effect_count):
        """Test that replay of completed invocation is blocked."""
        # Create and complete initial refund
        response = client.post(
            "/refunds",
            json={
                "account_id": "replay-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        assert response.status_code == 200
        body = response.json()
        assert body["executed"] is True
        invocation_id = body["invocation_id"]
        
        initial_effect_count = side_effect_count()
        assert initial_effect_count == 1
        
        # Attempt replay with same invocation ID
        replay_response = client.post(
            f"/replay/{invocation_id}",
            json={
                "account_id": "replay-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        # Should be blocked (409 Conflict)
        assert replay_response.status_code == 409
        replay_body = replay_response.json()
        assert replay_body["replay_blocked"] is True
        assert replay_body["execution_allowed"] is False
        assert replay_body["permit_issued"] is False
        assert replay_body["state_before"] == "completed"
        assert replay_body["state_after"] == "completed"
        assert replay_body["attempt_count_before"] == 1
        assert replay_body["attempt_count_after"] == 1
        
        # Verify no additional side effect
        final_effect_count = side_effect_count()
        assert final_effect_count == initial_effect_count

    def test_authorization_effect_may_still_be_allow_on_replay(self, client: TestClient, clear_side_effects):
        """Test that authorization decision could still be ALLOW on replay attempt."""
        # Create and complete initial refund
        response = client.post(
            "/refunds",
            json={
                "account_id": "replay-auth-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        assert response.status_code == 200
        invocation_id = response.json()["invocation_id"]
        
        # Attempt replay - authorization decision may still be ALLOW
        # but execution should be blocked
        replay_response = client.post(
            f"/replay/{invocation_id}",
            json={
                "account_id": "replay-auth-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        
        assert replay_response.status_code == 409
        body = replay_response.json()
        # Authorization effect could be 'allow', but execution must be blocked
        assert body["authorization_effect"] == "allow"
        assert body["execution_allowed"] is False
