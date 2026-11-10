from rest_framework_simplejwt.authentication import JWTAuthentication

from .csrf import enforce_request_csrf


class CookieJWT(JWTAuthentication):
    """Authenticate access cookies and enforce CSRF on unsafe requests."""

    def authenticate(self, request):
        """Authenticate credentials and apply the configured account policy."""
        raw_token = request.COOKIES.get("access_token")
        if not raw_token:
            return None
        token = self.get_validated_token(raw_token)
        user = self.get_user(token)
        enforce_request_csrf(request)
        return user, token
