from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from accounts.tokens import encoded_uid, make_token

PASSWORD = "A-long-secret!74"
NEW_PASSWORD = "Another-strong-secret!93"


def create_user(active=True, email="viewer@example.com"):
    return User.objects.create_user(
        username=email, email=email, password=PASSWORD, is_active=active
    )


def login_cookies(client, user):
    refresh = RefreshToken.for_user(user)
    client.cookies["refresh_token"] = str(refresh)
    client.cookies["access_token"] = str(refresh.access_token)
    return refresh


def link_path(user, purpose):
    endpoint = "activate" if purpose == "activation" else "password_confirm"
    return f"/api/{endpoint}/{encoded_uid(user)}/{make_token(user, purpose)}/"


class ApiCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_user()

    def post(self, path, data=None):
        return self.client.post(f"/api/{path}/", data or {}, format="json")

    def login(self):
        return self.post(
            "login", {"email": self.user.email, "password": PASSWORD}
        )
