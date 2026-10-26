"""CSRF protection for the Academy's tokenless cross-origin JSON client."""

from django.conf import settings
from rest_framework.authentication import SessionAuthentication


def trusted_json_request(request) -> bool:
    origin = request.headers.get("Origin")
    return (
        bool(origin)
        and origin in settings.CSRF_TRUSTED_JSON_ORIGINS
        and origin in settings.CSRF_TRUSTED_ORIGINS
        and origin in settings.CORS_ALLOWED_ORIGINS
        and request.content_type == "application/json"
        and request.headers.get("Sec-Fetch-Mode", "cors") == "cors"
        and "HTTP_X_CSRFTOKEN" not in request.META
    )


def enforce_request_csrf(request):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if trusted_json_request(request):
            return
    SessionAuthentication().enforce_csrf(request)
