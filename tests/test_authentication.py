from datetime import timedelta

from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .helpers import ApiCase, login_cookies


class AuthenticationTests(ApiCase):
    def test_login_response_and_cookies(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "detail": "Login successful",
                "user": {"id": self.user.pk, "username": self.user.email},
            },
        )
        assert_cookie_properties(response)

    @override_settings(COOKIE_SECURE=True, COOKIE_SAMESITE="None")
    def test_production_cookie_properties(self):
        response = self.login()
        self.assertTrue(response.cookies["access_token"]["secure"])
        self.assertEqual(response.cookies["access_token"]["samesite"], "None")

    def test_invalid_credentials_are_generic(self):
        existing = self.post(
            "login", {"email": self.user.email, "password": "wrong"}
        )
        missing = self.post(
            "login", {"email": "absent@example.com", "password": "wrong"}
        )
        self.assertEqual(existing.status_code, 400)
        self.assertEqual(existing.data, missing.data)

    def test_email_login_independent_of_admin_username(self):
        self.user.username = "admin-created-name"
        self.user.save()
        self.assertEqual(self.login().status_code, 200)

    def test_inactive_account(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login().status_code, 400)

    def test_protected_endpoint_requires_auth(self):
        self.assertEqual(self.client.get("/api/video/").status_code, 401)

    def test_cookie_authenticated_access(self):
        self.login()
        self.assertEqual(self.client.get("/api/video/").status_code, 200)

    def test_invalid_access_cookie(self):
        self.client.cookies["access_token"] = "bad"
        self.assertEqual(self.client.get("/api/video/").status_code, 401)

    def test_refresh_cookie_cannot_be_used_as_access(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies["access_token"] = str(refresh)
        self.assertEqual(self.client.get("/api/video/").status_code, 401)

    def test_successful_logout_deletes_cookies_and_blacklists(self):
        refresh = login_cookies(self.client, self.user)
        response = self.post("logout")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Refresh token is now invalid.", response.data["detail"])
        for name in ("access_token", "refresh_token"):
            self.assertEqual(response.cookies[name]["max-age"], 0)
        self.client.cookies["refresh_token"] = str(refresh)
        self.assertEqual(self.post("token/refresh").status_code, 401)
        self.assertEqual(self.post("logout").status_code, 401)

    def test_missing_logout_refresh(self):
        self.assertEqual(self.post("logout").status_code, 400)

    def test_valid_refresh_sets_new_access_cookie(self):
        login_cookies(self.client, self.user)
        response = self.post("token/refresh")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "Token refreshed")
        self.assertEqual(
            response.cookies["access_token"].value, response.data["access"]
        )
        self.client.cookies["access_token"] = response.data["access"]
        self.assertEqual(self.client.get("/api/video/").status_code, 200)

    def test_refresh_does_not_accept_body_tokens(self):
        token = str(RefreshToken.for_user(self.user))
        response = self.post("token/refresh", {"refresh": token})
        self.assertEqual(response.status_code, 400)

    def test_invalid_refresh(self):
        self.client.cookies["refresh_token"] = "invalid"
        self.assertEqual(self.post("token/refresh").status_code, 401)

    def test_expired_refresh(self):
        refresh = RefreshToken.for_user(self.user)
        refresh.set_exp(lifetime=timedelta(seconds=-1))
        self.client.cookies["refresh_token"] = str(refresh)
        self.assertEqual(self.post("token/refresh").status_code, 401)

    def test_expired_access(self):
        access = RefreshToken.for_user(self.user).access_token
        access.set_exp(lifetime=timedelta(seconds=-1))
        self.client.cookies["access_token"] = str(access)
        self.assertEqual(self.client.get("/api/video/").status_code, 401)

    def test_deactivated_user_cannot_refresh(self):
        login_cookies(self.client, self.user)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.post("token/refresh").status_code, 401)


class CsrfTests(ApiCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient(enforce_csrf_checks=True)

    def test_login_requires_csrf(self):
        self.assertEqual(self.login().status_code, 403)

    def test_cookie_endpoints_require_csrf(self):
        login_cookies(self.client, self.user)
        for path in ("logout", "token/refresh", "password_reset", "register"):
            with self.subTest(path=path):
                self.assertEqual(self.post(path).status_code, 403)

    def test_csrf_bootstrap_allows_login(self):
        response = self.client.get("/api/csrf/")
        self.assertIn("csrftoken", response.cookies)
        self.client.credentials(HTTP_X_CSRFTOKEN=response.data["csrfToken"])
        self.assertEqual(self.login().status_code, 200)

    def test_untrusted_origin_rejected(self):
        response = self.client.get("/api/csrf/")
        self.client.credentials(
            HTTP_X_CSRFTOKEN=response.data["csrfToken"],
            HTTP_ORIGIN="https://evil.example.com",
        )
        self.assertEqual(self.login().status_code, 403)

    def test_frontend_cors_credentials(self):
        response = self.client.options(
            "/api/login/",
            HTTP_ORIGIN="http://127.0.0.1:5500",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")
        self.assertEqual(
            response["Access-Control-Allow-Origin"], "http://127.0.0.1:5500"
        )


def assert_cookie_properties(response):
    for name in ("access_token", "refresh_token"):
        cookie = response.cookies[name]
        assert cookie["httponly"]
        assert cookie["path"] == "/api/"
        assert cookie["samesite"] == "Lax"
        assert cookie["max-age"] > 0
