from unittest.mock import patch

from django.core import mail
from django.test import override_settings

from accounts.models import EmailJob, User
from accounts.tasks import send_account_email
from accounts.tokens import encoded_uid, make_token

from .helpers import PASSWORD, ApiCase, link_path


class RegistrationTests(ApiCase):
    """Exercise registration behavior with isolated fixtures."""

    def setUp(self):
        """Prepare isolated fixtures and clients for each test."""
        super().setUp()
        self.data = {
            "email": "new@example.com",
            "password": PASSWORD,
            "confirmed_password": PASSWORD,
        }

    def register(self):
        """Submit registration data with optional test field overrides."""
        return self.post("register", self.data)

    def test_success_structure_and_inactive_hashed_password(self):
        """Verify success structure and inactive hashed password."""
        response = self.register()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.data), {"user", "token"})
        user = User.objects.get(email=self.data["email"])
        self.assertFalse(user.is_active)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertEqual(response.data["user"]["email"], user.email)
        self.assertNotIn("access_token", response.cookies)

    def test_duplicate_email_case_insensitive(self):
        """Verify duplicate email case insensitive."""
        self.data["email"] = self.user.email.upper()
        self.assertEqual(self.register().status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_email(self):
        """Verify invalid email."""
        self.data["email"] = "not-email"
        self.assertEqual(self.register().status_code, 400)

    def test_missing_fields(self):
        """Verify missing fields."""
        for field in self.data:
            with self.subTest(field=field):
                data = {
                    key: value
                    for key, value in self.data.items()
                    if key != field
                }
                self.assertEqual(self.post("register", data).status_code, 400)

    def test_different_passwords(self):
        """Verify different passwords."""
        self.data["confirmed_password"] = "different-password!"
        self.assertEqual(self.register().status_code, 400)

    def test_weak_passwords(self):
        """Verify weak passwords."""
        for password in (
            "123",
            "password",
            "12345678901234",
            "new@example.com",
        ):
            with self.subTest(password=password):
                self.data.update(
                    password=password, confirmed_password=password
                )
                self.assertEqual(self.register().status_code, 400)

    def test_activation_email_has_frontend_uid_and_token(self):
        """Verify activation email has frontend uid and token."""
        response = self.register()
        job = EmailJob.objects.get()
        send_account_email(job.pk)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn(
            "http://127.0.0.1:5500/pages/auth/activate.html?uid=", message.body
        )
        self.assertIn(encoded_uid(job.user), message.body)
        self.assertIn(response.data["token"], message.body)
        self.assertEqual(message.alternatives[0].mimetype, "text/html")
        self.assertEqual(message.to, [self.data["email"]])

    def test_email_delivery_idempotent(self):
        """Verify email delivery idempotent."""
        self.register()
        job = EmailJob.objects.get()
        send_account_email(job.pk)
        send_account_email(job.pk)
        self.assertEqual(len(mail.outbox), 1)

    def test_valid_activation(self):
        """Verify valid activation."""
        self.user.is_active = False
        self.user.save()
        response = self.client.get(link_path(self.user, "activation"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["message"], "Account successfully activated."
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_activation_cannot_be_reused(self):
        """Verify activation cannot be reused."""
        self.user.is_active = False
        self.user.save()
        path = link_path(self.user, "activation")
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 400)

    def test_invalid_activation_token(self):
        """Verify invalid activation token."""
        uid = encoded_uid(self.user)
        self.assertEqual(
            self.client.get(f"/api/activate/{uid}/bad/").status_code, 400
        )

    def test_invalid_uid(self):
        """Verify invalid uid."""
        self.assertEqual(
            self.client.get("/api/activate/invalid/bad/").status_code, 400
        )

    @override_settings(ACTIVATION_TIMEOUT=10)
    def test_expired_activation(self):
        """Verify expired activation."""
        self.user.is_active = False
        self.user.save()
        with patch("django.core.signing.time.time", return_value=100):
            path = link_path(self.user, "activation")
        with patch("django.core.signing.time.time", return_value=111):
            self.assertEqual(self.client.get(path).status_code, 400)

    def test_reset_token_cannot_activate(self):
        """Verify reset token cannot activate."""
        self.user.is_active = False
        self.user.save()
        path = (
            f"/api/activate/{encoded_uid(self.user)}/"
            f"{make_token(self.user, 'reset')}/"
        )
        self.assertEqual(self.client.get(path).status_code, 400)
