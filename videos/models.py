import uuid
from pathlib import Path

from django.core.validators import FileExtensionValidator
from django.db import models

from .storage import private_storage


def upload_path(instance, filename: str) -> str:
    """Generate a unique source path with its original extension."""
    return f"uploads/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class Video(models.Model):
    """Store a video source, public thumbnail and private HLS state."""

    class Status(models.TextChoices):
        """Describe the durable video processing lifecycle."""

        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    title = models.CharField("Video title", max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=80, db_index=True)
    upload = models.FileField(
        "Original video",
        storage=private_storage,
        upload_to=upload_path,
        validators=[FileExtensionValidator(["mp4", "mov", "mkv", "webm"])],
    )
    thumbnail = models.ImageField(
        "Thumbnail image", upload_to="thumbnails/", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(
        "Processing status",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    resolutions = models.JSONField(
        "Available HLS resolutions", default=list, blank=True
    )
    error = models.CharField("Processing error", max_length=128, blank=True)
    job_id = models.CharField("RQ job ID", max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Video"
        verbose_name_plural = "Videos"
