from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Configure account models and authentication services."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
