"""Safety and failure checks for the opt-in live infrastructure acceptance."""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from scripts import verify_infrastructure as acceptance


class AcceptanceSafetyTests(SimpleTestCase):
    """Exercise acceptance safety behavior with isolated fixtures."""

    def test_sqlite_is_rejected_before_network_or_writes(self):
        """Verify sqlite is rejected before network or writes."""
        database = SimpleNamespace(vendor="sqlite")
        with patch.object(acceptance, "connection", database):
            with self.assertRaisesMessage(CommandError, "Real PostgreSQL"):
                acceptance.main()

    def test_normal_database_is_rejected(self):
        """Verify normal database is rejected."""
        database = SimpleNamespace(
            vendor="postgresql", settings_dict={"NAME": "videoflix"}
        )
        with patch.object(acceptance, "connection", database):
            with self.assertRaisesMessage(CommandError, "_acceptance"):
                acceptance.verify_isolation()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
    )
    def test_smtp_is_rejected_even_on_acceptance_database(self):
        """Verify smtp is rejected even on acceptance database."""
        database = SimpleNamespace(
            vendor="postgresql", settings_dict={"NAME": "qa_acceptance"}
        )
        with patch.object(acceptance, "connection", database):
            with self.assertRaisesMessage(CommandError, "SMTP is forbidden"):
                acceptance.verify_isolation()

    def test_worker_failure_is_reported_without_waiting(self):
        """Verify worker failure is reported without waiting."""
        instance = SimpleNamespace(
            status="failed", refresh_from_db=lambda: None
        )
        with self.assertRaisesMessage(CommandError, "task failure"):
            acceptance.wait_for_status(instance, "ready")

    def test_worker_timeout_is_reported(self):
        """Verify worker timeout is reported."""
        instance = SimpleNamespace(status="pending")
        with self.assertRaisesMessage(CommandError, "before timeout"):
            acceptance.wait_for_status(instance, "ready", timeout=0)
