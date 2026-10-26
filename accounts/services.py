from functools import partial

from django.db import IntegrityError, transaction
from django.utils.http import urlsafe_base64_decode
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from .models import EmailJob, User
from .tokens import make_token, valid_token


@transaction.atomic
def register_user(data: dict) -> tuple:
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=data["email"],
                email=data["email"],
                password=data["password"],
                is_active=False,
            )
    except IntegrityError as error:
        raise ValidationError(
            "Registration could not be completed."
        ) from error
    return user, schedule_email(user, "activation")


def schedule_email(user, purpose: str) -> str:
    from .tasks import enqueue_email

    token = make_token(user, purpose)
    job = EmailJob.objects.create(user=user, purpose=purpose, token=token)
    transaction.on_commit(partial(enqueue_email, job.pk))
    return token


def locked_user(uid: str):
    try:
        user_id = urlsafe_base64_decode(uid).decode()
        return User.objects.select_for_update().get(pk=int(user_id))
    except (ValueError, OverflowError, UnicodeDecodeError, User.DoesNotExist):
        raise ValidationError("Invalid or expired link.") from None


@transaction.atomic
def activate_user(uid: str, token: str):
    user = locked_user(uid)
    if user.is_active or not valid_token(user, token, "activation"):
        raise ValidationError("Invalid or expired link.")
    user.is_active = True
    user.save(update_fields=["is_active"])


def request_reset(email: str):
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user and user.has_usable_password():
        schedule_email(user, "reset")


@transaction.atomic
def confirm_password(uid: str, token: str, data: dict):
    from .serializers import ConfirmSerializer

    user = locked_user(uid)
    if not user.is_active or not valid_token(user, token, "reset"):
        raise ValidationError("Invalid or expired link.")
    serializer = ConfirmSerializer(data=data, context={"user": user})
    serializer.is_valid(raise_exception=True)
    user.set_password(serializer.validated_data["new_password"])
    user.save(update_fields=["password"])


def cookie_refresh(request):
    raw_token = request.COOKIES.get("refresh_token")
    if not raw_token:
        raise ValidationError("Refresh token is required.")
    try:
        token = RefreshToken(raw_token)
        JWTAuthentication().get_user(token.access_token)
        serializer = TokenRefreshSerializer(data={"refresh": raw_token})
        serializer.is_valid(raise_exception=True)
        return token, serializer.validated_data["access"]
    except TokenError as error:
        raise AuthenticationFailed("Invalid refresh token.") from error
