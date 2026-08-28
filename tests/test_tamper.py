"""Test tamper detection for Ruhusa v0.7.0.

NOTE: These tests are designed to use an isolated test database.
They should NOT be run against shared development/production data.
"""

import os
import pytest

# Mark all tests in this module as requiring postgres
pytestmark = pytest.mark.postgres


@pytest.mark.postgres
class TestTamperDetection:
    """Test that audit chain tamper is detected.
    
    WARNING: These tests modify audit data directly. Only use with
    an isolated test database.
    """

    def test_tamper_detection_requires_isolated_database(self):
        """Test tamper detection against isolated database.
        
        To run this test:
        1. Create isolated database: psql -U postgres -c "CREATE DATABASE ruhusa_test_tamper;"
        2. Set DSN: export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_test_tamper"
        3. Run: uv run pytest tests/test_tamper.py -v
        """
        # Implementation: To test tamper detection:
        # 1. Create an isolated test database
        # 2. Generate audit events via authorization decisions
        # 3. Verify verify_chain() returns True
        # 4. Modify an audit value directly in PostgreSQL:
        #    UPDATE ruhusa_audit_log SET decision_effect = 'deny' WHERE id = 1;
        # 5. Verify verify_chain() returns False
        # 
        # This test is intentionally skipped until infrastructure
        # supports isolated database creation and cleanup.
        
        pytest.skip(
            "Tamper detection requires isolated PostgreSQL database. "
            "Create test database and run manually with dedicated DSN."
        )
