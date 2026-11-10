from django.core.signals import request_finished
from django.db import close_old_connections
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from accounts.tokens import encoded_uid, make_token

PASSWORD = "A-long-secret!74"
NEW_PASSWORD = "Another-strong-secret!93"


def create_user(active=True, email="viewer@example.com"):
    """Create a synthetic viewer with a known test password."""
    return User.objects.create_user(
        username=email, email=email, password=PASSWORD, is_active=active
    )


def login_cookies(client, user):
    """Authenticate an API test client using real signed token cookies."""
    refresh = RefreshToken.for_user(user)
    client.cookies["refresh_token"] = str(refresh)
    client.cookies["access_token"] = str(refresh.access_token)
    return refresh


def link_path(user, purpose):
    """Build a valid action endpoint for a synthetic test account."""
    endpoint = "activate" if purpose == "activation" else "password_confirm"
    return f"/api/{endpoint}/{encoded_uid(user)}/{make_token(user, purpose)}/"


def close_response(response):
    """Close test streams without closing a surrounding test transaction."""
    request_finished.disconnect(close_old_connections)
    try:
        response.close()
    finally:
        request_finished.connect(close_old_connections)


def streamed_bytes(response):
    """Read and close a test stream while preserving its transaction."""
    try:
        return b"".join(response.streaming_content)
    finally:
        close_response(response)


class ApiCase(TestCase):
    """Provide a test viewer and reusable JSON authentication helpers."""

    def setUp(self):
        """Prepare isolated fixtures and clients for each test."""
        self.client = APIClient()
        self.user = create_user()

    def post(self, path, data=None):
        """Submit a JSON request using the configured test client."""
        return self.client.post(f"/api/{path}/", data or {}, format="json")

    def login(self):
        """Submit the synthetic viewer email and password to the login API."""
        return self.post(
            "login", {"email": self.user.email, "password": PASSWORD}
        )
