from django.middleware.csrf import get_token, rotate_token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .cookies import clear_cookies, set_access_cookie, set_login_cookies
from .csrf import enforce_request_csrf
from .serializers import LoginSerializer, RegisterSerializer, ResetSerializer
from .services import (
    activate_user,
    confirm_password,
    cookie_refresh,
    register_user,
    request_reset,
)


class PublicView(APIView):
    """Apply CSRF policy to unauthenticated account endpoints."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        """Initialize the API request and enforce the account CSRF policy."""
        super().initial(request, *args, **kwargs)
        enforce_request_csrf(request)

    def get_authenticate_header(self, request):
        """Advertise bearer authentication for rejected API requests."""
        return "Bearer"


class CsrfView(PublicView):
    """Provide a CSRF token for clients using Django token protection."""

    def get(self, request):
        """Return a CSRF token for subsequent protected requests."""
        return Response({"csrfToken": get_token(request)})


class RegisterView(PublicView):
    """Create an inactive account and schedule its activation email."""

    def post(self, request):
        """Validate registration and return the newly scheduled activation."""
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, token = register_user(serializer.validated_data)
        return Response(
            {"user": {"id": user.pk, "email": user.email}, "token": token},
            status=201,
        )


class ActivateView(PublicView):
    """Activate an account using its signed single-use link."""

    def get(self, request, uidb64, token):
        """Activate the account identified by the signed URL."""
        activate_user(uidb64, token)
        return Response({"message": "Account successfully activated."})


class LoginView(PublicView):
    """Issue access and refresh cookies after email authentication."""

    def post(self, request):
        """Validate email credentials and issue authentication cookies."""
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        rotate_token(request)
        response = Response(
            {
                "detail": "Login successful",
                "user": {"id": user.pk, "username": user.email},
            }
        )
        return set_login_cookies(response, refresh)


class LogoutView(PublicView):
    """Blacklist the refresh token and expire authentication cookies."""

    def post(self, request):
        """Revoke refresh credentials and clear authentication cookies."""
        refresh, _ = cookie_refresh(request)
        refresh.blacklist()
        response = Response(
            {
                "detail": (
                    "Logout successful! All tokens will be deleted. "
                    "Refresh token is now invalid."
                )
            }
        )
        return clear_cookies(response)


class RefreshView(PublicView):
    """Refresh access credentials using the refresh cookie."""

    def post(self, request):
        """Issue a new access cookie from a valid refresh cookie."""
        _, access = cookie_refresh(request)
        response = Response({"detail": "Token refreshed", "access": access})
        return set_access_cookie(response, AccessToken(access))


class PasswordResetView(PublicView):
    """Request recovery without revealing whether an account exists."""

    def post(self, request):
        """Validate the address and return a generic recovery response."""
        serializer = ResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_reset(serializer.validated_data["email"])
        return Response(
            {"detail": "An email has been sent to reset your password."}
        )


class PasswordConfirmView(PublicView):
    """Change the password after validating a recovery link."""

    def post(self, request, uidb64, token):
        """Apply a validated recovery password and confirm completion."""
        confirm_password(uidb64, token, request.data)
        return Response(
            {"detail": "Your Password has been successfully reset."}
        )
