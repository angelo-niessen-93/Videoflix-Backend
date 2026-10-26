from django.conf import settings
from django.core import signing
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def user_state(user) -> str:
    value = f"{user.pk}:{user.password}:{user.is_active}"
    return salted_hmac("account-state", value).hexdigest()


def make_token(user, purpose: str) -> str:
    return signing.dumps(
        {"uid": user.pk, "state": user_state(user)}, salt=purpose
    )


def valid_token(user, token: str, purpose: str) -> bool:
    timeout = (
        settings.ACTIVATION_TIMEOUT
        if purpose == "activation"
        else settings.PASSWORD_RESET_TIMEOUT
    )
    try:
        data = signing.loads(token, salt=purpose, max_age=timeout)
        return data["uid"] == user.pk and constant_time_compare(
            data["state"], user_state(user)
        )
    except (signing.BadSignature, KeyError, TypeError):
        return False


def encoded_uid(user) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))
