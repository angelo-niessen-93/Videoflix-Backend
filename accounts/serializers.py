from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User


def check_password_pair(data, first: str, second: str, user) -> dict:
    """Reject mismatched passwords and apply Django password validators."""
    if data[first] != data[second]:
        raise serializers.ValidationError("Passwords do not match.")
    try:
        validate_password(data[first], user=user)
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.messages) from error
    return data


class RegisterSerializer(serializers.Serializer):
    """Validate registration email and matching strong passwords."""

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirmed_password = serializers.CharField(
        write_only=True, trim_whitespace=False
    )

    def validate(self, data):
        """Normalize the email and validate matching registration passwords."""
        data["email"] = data["email"].lower()
        user = User(email=data["email"], username=data["email"])
        return check_password_pair(
            data, "password", "confirmed_password", user
        )


class LoginSerializer(serializers.Serializer):
    """Validate email credentials and return an authenticated user."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, data):
        """Authenticate the email and reject invalid credentials uniformly."""
        user = authenticate(
            username=data["email"].lower(), password=data["password"]
        )
        if user is None:
            raise serializers.ValidationError("Invalid credentials.")
        return {"user": user}


class ResetSerializer(serializers.Serializer):
    """Validate the address supplied for password recovery."""

    email = serializers.EmailField()


class ConfirmSerializer(serializers.Serializer):
    """Validate a matching password pair against the target account."""

    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False
    )
    confirm_password = serializers.CharField(
        write_only=True, trim_whitespace=False
    )

    def validate(self, data):
        """Validate recovery passwords against the target account."""
        return check_password_pair(
            data, "new_password", "confirm_password", self.context["user"]
        )
