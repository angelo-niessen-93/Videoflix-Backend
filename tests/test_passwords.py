from unittest.mock import patch

from django.core import mail
from django.test import override_settings

from accounts.models import EmailJob
from accounts.tasks import send_account_email
from accounts.tokens import encoded_uid, make_token

from .helpers import NEW_PASSWORD, PASSWORD, ApiCase, link_path, login_cookies


class PasswordTests(ApiCase):
    """Exercise password behavior with isolated fixtures."""

    def setUp(self):
        """Prepare isolated fixtures and clients for each test."""
        super().setUp()
        self.path = link_path(self.user, "reset")
        self.data = {
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        }

    def confirm(self):
        """Submit a recovery token with overridable password fields."""
        return self.client.post(self.path, self.data, format="json")

    def test_generic_reset_response(self):
        """Verify generic reset response."""
        known = self.post("password_reset", {"email": self.user.email})
        missing = self.post("password_reset", {"email": "missing@example.com"})
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.data, missing.data)
        self.assertEqual(
            known.data["detail"],
            "An email has been sent to reset your password.",
        )
        self.assertEqual(EmailJob.objects.count(), 1)

    def test_invalid_reset_email(self):
        """Verify invalid reset email."""
        self.assertEqual(
            self.post("password_reset", {"email": "bad"}).status_code, 400
        )

    def test_inactive_user_receives_no_reset_mail(self):
        """Verify inactive user receives no reset mail."""
        self.user.is_active = False
        self.user.save()
        self.assertEqual(
            self.post(
                "password_reset", {"email": self.user.email}
            ).status_code,
            200,
        )
        self.assertFalse(EmailJob.objects.exists())

    def test_reset_mail_contains_valid_frontend_link(self):
        """Verify reset mail contains valid frontend link."""
        self.post("password_reset", {"email": self.user.email})
        job = EmailJob.objects.get()
        send_account_email(job.pk)
        self.assertIn(
            "http://127.0.0.1:5500/pages/auth/confirm_password.html?uid=",
            mail.outbox[0].body,
        )
        self.assertIn(job.token, mail.outbox[0].body)
        self.assertIn(encoded_uid(self.user), mail.outbox[0].body)
        path = f"/api/password_confirm/{encoded_uid(self.user)}/{job.token}/"
        self.assertEqual(self.client.post(path, self.data).status_code, 200)

    def test_password_change_and_new_login(self):
        """Verify password change and new login."""
        self.assertEqual(self.confirm().status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(self.user.check_password(PASSWORD))
        self.assertEqual(self.login().status_code, 400)
        self.assertEqual(
            self.post(
                "login", {"email": self.user.email, "password": NEW_PASSWORD}
            ).status_code,
            200,
        )

    def test_reset_token_single_use(self):
        """Verify reset token single use."""
        self.assertEqual(self.confirm().status_code, 200)
        self.assertEqual(self.confirm().status_code, 400)

    def test_mismatched_passwords(self):
        """Verify mismatched passwords."""
        self.data["confirm_password"] = "different-password!"
        self.assertEqual(self.confirm().status_code, 400)

    def test_weak_new_password(self):
        """Verify weak new password."""
        self.data = {"new_password": "123", "confirm_password": "123"}
        self.assertEqual(self.confirm().status_code, 400)

    def test_missing_password_fields(self):
        """Verify missing password fields."""
        self.data = {}
        self.assertEqual(self.confirm().status_code, 400)

    def test_invalid_token(self):
        """Verify invalid token."""
        self.path = f"/api/password_confirm/{encoded_uid(self.user)}/bad/"
        self.assertEqual(self.confirm().status_code, 400)

    def test_activation_token_cannot_reset_password(self):
        """Verify activation token cannot reset password."""
        token = make_token(self.user, "activation")
        self.path = f"/api/password_confirm/{encoded_uid(self.user)}/{token}/"
        self.assertEqual(self.confirm().status_code, 400)

    @override_settings(PASSWORD_RESET_TIMEOUT=10)
    def test_expired_reset_token(self):
        """Verify expired reset token."""
        with patch("django.core.signing.time.time", return_value=100):
            self.path = link_path(self.user, "reset")
        with patch("django.core.signing.time.time", return_value=111):
            self.assertEqual(self.confirm().status_code, 400)

    def test_reset_revokes_old_access_and_refresh(self):
        """Verify reset revokes old access and refresh."""
        login_cookies(self.client, self.user)
        self.assertEqual(self.confirm().status_code, 200)
        self.assertEqual(self.client.get("/api/video/").status_code, 401)
        self.assertEqual(self.post("token/refresh").status_code, 401)
