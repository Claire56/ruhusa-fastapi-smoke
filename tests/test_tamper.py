"""Test tamper detection for Ruhusa v0.7.0.

NOTE: These tests are designed to use an isolated test database.
They should NOT be run against shared development/production data.
"""

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
        """Placeholder: tamper tests require isolated PostgreSQL."""
        # Implementation note: To test tamper detection:
        # 1. Create an isolated test database
        # 2. Generate audit events
        # 3. Verify verify_chain() returns True
        # 4. Modify an audit value directly in PostgreSQL
        # 5. Verify verify_chain() returns False
        # 
        # Example:
        # UPDATE ruhusa_audit_log SET decision_effect = 'deny' WHERE id = 1;
        # Verify chain is now broken
        pass
