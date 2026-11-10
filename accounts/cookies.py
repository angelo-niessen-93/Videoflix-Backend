from django.conf import settings

COOKIE_PATH = "/api/"


def set_token_cookie(response, name: str, token, lifetime):
    """Set an HttpOnly API cookie using configured security attributes."""
    response.set_cookie(
        name,
        str(token),
        max_age=int(lifetime.total_seconds()),
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )
    return response


def set_login_cookies(response, refresh):
    """Attach refresh and access cookies to a login response."""
    set_token_cookie(response, "refresh_token", refresh, refresh.lifetime)
    return set_access_cookie(response, refresh.access_token)


def set_access_cookie(response, token):
    """Attach the current access token to the response."""
    return set_token_cookie(response, "access_token", token, token.lifetime)


def clear_cookies(response):
    """Expire both authentication cookies at their original API path."""
    for name in ("access_token", "refresh_token"):
        response.delete_cookie(
            name, path=COOKIE_PATH, samesite=settings.COOKIE_SAMESITE
        )
    return response
