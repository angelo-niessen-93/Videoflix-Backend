from unittest.mock import patch

from django.core import mail
from django.test import override_settings

from accounts.models import EmailJob, User
from accounts.tasks import send_account_email
from accounts.tokens import encoded_uid, make_token

from .helpers import PASSWORD, ApiCase, link_path


class RegistrationTests(ApiCase):
    def setUp(self):
        super().setUp()
        self.data = {
            "email": "new@example.com",
            "password": PASSWORD,
            "confirmed_password": PASSWORD,
        }

    def register(self):
        return self.post("register", self.data)

    def test_success_structure_and_inactive_hashed_password(self):
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
        self.data["email"] = self.user.email.upper()
        self.assertEqual(self.register().status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_email(self):
        self.data["email"] = "not-email"
        self.assertEqual(self.register().status_code, 400)

    def test_missing_fields(self):
        for field in self.data:
            with self.subTest(field=field):
                data = {
                    key: value
                    for key, value in self.data.items()
                    if key != field
                }
                self.assertEqual(self.post("register", data).status_code, 400)

    def test_different_passwords(self):
        self.data["confirmed_password"] = "different-password!"
        self.assertEqual(self.register().status_code, 400)

    def test_weak_passwords(self):
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
        self.register()
        job = EmailJob.objects.get()
        send_account_email(job.pk)
        send_account_email(job.pk)
        self.assertEqual(len(mail.outbox), 1)

    def test_valid_activation(self):
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
        self.user.is_active = False
        self.user.save()
        path = link_path(self.user, "activation")
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 400)

    def test_invalid_activation_token(self):
        uid = encoded_uid(self.user)
        self.assertEqual(
            self.client.get(f"/api/activate/{uid}/bad/").status_code, 400
        )

    def test_invalid_uid(self):
        self.assertEqual(
            self.client.get("/api/activate/invalid/bad/").status_code, 400
        )

    @override_settings(ACTIVATION_TIMEOUT=10)
    def test_expired_activation(self):
        self.user.is_active = False
        self.user.save()
        with patch("django.core.signing.time.time", return_value=100):
            path = link_path(self.user, "activation")
        with patch("django.core.signing.time.time", return_value=111):
            self.assertEqual(self.client.get(path).status_code, 400)

    def test_reset_token_cannot_activate(self):
        self.user.is_active = False
        self.user.save()
        path = (
            f"/api/activate/{encoded_uid(self.user)}/"
            f"{make_token(self.user, 'reset')}/"
        )
        self.assertEqual(self.client.get(path).status_code, 400)
