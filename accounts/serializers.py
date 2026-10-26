from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User


def check_password_pair(data, first: str, second: str, user) -> dict:
    if data[first] != data[second]:
        raise serializers.ValidationError("Passwords do not match.")
    try:
        validate_password(data[first], user=user)
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.messages) from error
    return data


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirmed_password = serializers.CharField(
        write_only=True, trim_whitespace=False
    )

    def validate(self, data):
        data["email"] = data["email"].lower()
        user = User(email=data["email"], username=data["email"])
        return check_password_pair(
            data, "password", "confirmed_password", user
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, data):
        user = authenticate(
            username=data["email"].lower(), password=data["password"]
        )
        if user is None:
            raise serializers.ValidationError("Invalid credentials.")
        return {"user": user}


class ResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ConfirmSerializer(serializers.Serializer):
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False
    )
    confirm_password = serializers.CharField(
        write_only=True, trim_whitespace=False
    )

    def validate(self, data):
        return check_password_pair(
            data, "new_password", "confirm_password", self.context["user"]
        )
