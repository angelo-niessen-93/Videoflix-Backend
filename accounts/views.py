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
    authentication_classes = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        enforce_request_csrf(request)

    def get_authenticate_header(self, request):
        return "Bearer"


class CsrfView(PublicView):
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterView(PublicView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, token = register_user(serializer.validated_data)
        return Response(
            {"user": {"id": user.pk, "email": user.email}, "token": token},
            status=201,
        )


class ActivateView(PublicView):
    def get(self, request, uidb64, token):
        activate_user(uidb64, token)
        return Response({"message": "Account successfully activated."})


class LoginView(PublicView):
    def post(self, request):
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
    def post(self, request):
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
    def post(self, request):
        _, access = cookie_refresh(request)
        response = Response({"detail": "Token refreshed", "access": access})
        return set_access_cookie(response, AccessToken(access))


class PasswordResetView(PublicView):
    def post(self, request):
        serializer = ResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_reset(serializer.validated_data["email"])
        return Response(
            {"detail": "An email has been sent to reset your password."}
        )


class PasswordConfirmView(PublicView):
    def post(self, request, uidb64, token):
        confirm_password(uidb64, token, request.data)
        return Response(
            {"detail": "Your Password has been successfully reset."}
        )
