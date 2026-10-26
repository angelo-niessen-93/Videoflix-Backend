from rest_framework_simplejwt.authentication import JWTAuthentication

from .csrf import enforce_request_csrf


class CookieJWT(JWTAuthentication):
    def authenticate(self, request):
        raw_token = request.COOKIES.get("access_token")
        if not raw_token:
            return None
        token = self.get_validated_token(raw_token)
        user = self.get_user(token)
        enforce_request_csrf(request)
        return user, token
