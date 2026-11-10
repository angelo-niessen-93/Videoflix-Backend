from django.apps import AppConfig


class VideosConfig(AppConfig):
    """Register video processing signals at application startup."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "videos"

    def ready(self):
        """Register video signal receivers after application initialization."""
        from . import signals  # noqa: F401
