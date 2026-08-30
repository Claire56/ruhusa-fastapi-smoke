"""Audit tamper-evidence validation.

This file intentionally corrupts audit data and therefore must run only against
an isolated disposable PostgreSQL database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app, runtime
from tests.postgres_control import require_destructive_opt_in


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.tamper,
]


def test_historical_audit_mutation_breaks_chain_verification():
    require_destructive_opt_in()
    assert runtime.backend == "postgres"

    # Keep ALL pool operations inside the TestClient context so the pool stays
    # open for every step.  The shutdown handler closes the pool when the
    # 'with' block exits, so nothing must touch the pool after that point.
    with TestClient(app) as client:
        # Step 1: reset audit table to a known-clean state
        with runtime.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM ruhusa_audit_events")
                cur.execute(
                    """
                    UPDATE ruhusa_audit_chain
                    SET last_sequence = 0, last_hash = 'GENESIS'
                    WHERE singleton = TRUE
                    """
                )

        # Step 2: create two authorized refunds (≥ 4 audit events incl. revalidation)
        first = client.post(
            "/refunds",
            json={
                "account_id": "tamper-evidence-1",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        second = client.post(
            "/refunds",
            json={
                "account_id": "tamper-evidence-2",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        assert first.status_code == 200
        assert second.status_code == 200

        # Step 3: chain must be valid before mutation
        assert runtime.audit_log.verify_chain() is True
        assert len(runtime.audit_log.snapshot()) >= 4

        # Step 4: directly mutate the stored reason for sequence = 1
        with runtime.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ruhusa_audit_events
                    SET reason = reason || ' [TAMPERED]'
                    WHERE sequence = 1
                    """
                )
                assert cur.rowcount == 1

        # Step 5: chain must now be broken
        assert runtime.audit_log.verify_chain() is False
