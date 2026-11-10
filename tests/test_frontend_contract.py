from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import EmailJob, User
from accounts.services import schedule_email
from accounts.tasks import send_account_email

from .helpers import PASSWORD, ApiCase, login_cookies

FRONTEND_ORIGIN = "http://127.0.0.1:5500"


class FrontendRequestTests(ApiCase):
    """Exercise frontend request behavior with isolated fixtures."""

    def setUp(self):
        """Prepare isolated fixtures and clients for each test."""
        super().setUp()
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.credentials(HTTP_ORIGIN=FRONTEND_ORIGIN)

    def test_registration_json_without_csrf_bootstrap(self):
        """Verify registration json without csrf bootstrap."""
        response = self.post(
            "register",
            {
                "email": "official@example.com",
                "password": PASSWORD,
                "confirmed_password": PASSWORD,
                "privacy_policy": "on",
            },
        )
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="official@example.com")
        self.assertFalse(user.is_active)

    def test_login_refresh_logout_without_csrf_header(self):
        """Verify login refresh logout without csrf header."""
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.post("token/refresh").status_code, 200)
        response = self.post("logout")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies["access_token"]["max-age"], 0)

    def test_untrusted_origins_blocked_without_csrf_header(self):
        """Verify untrusted origins blocked without csrf header."""
        for origin in (
            "null",
            "http://evil.example.com",
            "",
            "http://127.0.0.1:5500.evil.test",
            "http://127.0.0.1:5501",
            "http://localhost:5500",
        ):
            with self.subTest(origin=origin):
                self.client.credentials(HTTP_ORIGIN=origin)
                self.assertEqual(self.login().status_code, 403)

    def test_simple_form_posts_remain_csrf_protected(self):
        """Verify simple form posts remain csrf protected."""
        for content_type in (
            "text/plain",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        ):
            with self.subTest(content_type=content_type):
                response = self.client.post(
                    "/api/login/",
                    "email=viewer@example.com",
                    content_type=content_type,
                )
                self.assertEqual(response.status_code, 403)

    def test_incorrect_explicit_csrf_header_not_ignored(self):
        """Verify incorrect explicit csrf header not ignored."""
        self.client.credentials(
            HTTP_ORIGIN=FRONTEND_ORIGIN, HTTP_X_CSRFTOKEN="invalid"
        )
        self.assertEqual(self.login().status_code, 403)

    def test_navigation_cannot_use_tokenless_json_policy(self):
        """Verify navigation cannot use tokenless json policy."""
        self.client.credentials(
            HTTP_ORIGIN=FRONTEND_ORIGIN, HTTP_SEC_FETCH_MODE="navigate"
        )
        self.assertEqual(self.login().status_code, 403)

    @override_settings(CSRF_TRUSTED_JSON_ORIGINS=[])
    def test_token_policy_can_be_required(self):
        """Verify token policy can be required."""
        self.assertEqual(self.login().status_code, 403)

    @override_settings(CORS_ALLOWED_ORIGINS=[])
    def test_origin_must_also_be_cors_allowed(self):
        """Verify origin must also be cors allowed."""
        self.assertEqual(self.login().status_code, 403)

    @override_settings(CSRF_TRUSTED_ORIGINS=[])
    def test_origin_must_also_be_csrf_trusted(self):
        """Verify origin must also be csrf trusted."""
        self.assertEqual(self.login().status_code, 403)

    def test_access_lifetime_exceeds_twenty_minute_refresh_interval(self):
        """Verify access lifetime exceeds twenty minute refresh interval."""
        response = self.login()
        cookie = response.cookies["access_token"]
        self.assertGreater(cookie["max-age"], 20 * 60)
        refresh = RefreshToken.for_user(self.user)
        access = refresh.access_token
        self.assertEqual(access["exp"] - access["iat"], 30 * 60)

    def test_eight_character_strong_password_matches_frontend(self):
        """Verify eight character strong password matches frontend."""
        response = self.post(
            "register",
            {
                "email": "eight@example.com",
                "password": "J4!qx9Z@",
                "confirmed_password": "J4!qx9Z@",
            },
        )
        self.assertEqual(response.status_code, 201)

    def test_revocation_still_applies_to_trusted_origin(self):
        """Verify revocation still applies to trusted origin."""
        refresh = login_cookies(self.client, self.user)
        self.assertEqual(self.post("logout").status_code, 200)
        self.client.cookies["refresh_token"] = str(refresh)
        self.assertEqual(self.post("token/refresh").status_code, 401)


class OfficialEmailTests(ApiCase):
    """Exercise official email behavior with isolated fixtures."""

    def send_email(self, purpose):
        """Deliver a scheduled account email to the test mail backend."""
        schedule_email(self.user, purpose)
        send_account_email(EmailJob.objects.get().pk)
        return mail.outbox[-1]

    def test_official_activation_page_and_query_parameters(self):
        """Verify official activation page and query parameters."""
        message = self.send_email("activation")
        link = next(
            word for word in message.body.split() if word.startswith("http://")
        )
        self.assertEqual(urlsplit(link).path, "/pages/auth/activate.html")
        self.assertEqual(set(parse_qs(urlsplit(link).query)), {"uid", "token"})
        self.assertTrue(link.startswith(FRONTEND_ORIGIN))

    def test_official_reset_page_and_query_parameters(self):
        """Verify official reset page and query parameters."""
        message = self.send_email("reset")
        link = next(
            word for word in message.body.split() if word.startswith("http://")
        )
        self.assertEqual(
            urlsplit(link).path, "/pages/auth/confirm_password.html"
        )
        self.assertEqual(set(parse_qs(urlsplit(link).query)), {"uid", "token"})

    def test_inline_logo_and_responsive_mail_structure(self):
        """Verify inline logo and responsive mail structure."""
        message = self.send_email("activation")
        html = message.alternatives[0].content
        self.assertIn('role="presentation"', html)
        self.assertIn('name="viewport"', html)
        self.assertIn("cid:videoflix-logo", html)
        logo = message.attachments[0]
        self.assertEqual(logo.get_content_type(), "image/png")
        self.assertEqual(logo["Content-ID"], "<videoflix-logo>")
        self.assertTrue(logo.get_payload(decode=True).startswith(b"\x89PNG"))

    def test_reset_design_and_expiration_match_settings(self):
        """Verify reset design and expiration match settings."""
        message = self.send_email("reset")
        self.assertEqual(message.subject, "Reset your Password")
        minutes = settings.PASSWORD_RESET_TIMEOUT // 60
        self.assertIn(f"{minutes} minutes", message.body)
        self.assertIn(f"{minutes} minutes", message.alternatives[0].content)

    def test_outlook_fallback_and_plaintext_are_present(self):
        """Verify outlook fallback and plaintext are present."""
        message = self.send_email("activation")
        self.assertIn("<v:roundrect", message.alternatives[0].content)
        self.assertIn("Thank you for registering", message.body)
        self.assertNotIn("<table", message.body)
