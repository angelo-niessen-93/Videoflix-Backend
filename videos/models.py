import uuid
from pathlib import Path

from django.core.validators import FileExtensionValidator
from django.db import models

from .storage import private_storage


def upload_path(instance, filename: str) -> str:
    return f"uploads/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class Video(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=80, db_index=True)
    upload = models.FileField(
        storage=private_storage,
        upload_to=upload_path,
        validators=[FileExtensionValidator(["mp4", "mov", "mkv", "webm"])],
    )
    thumbnail = models.ImageField(upload_to="thumbnails/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    resolutions = models.JSONField(default=list, blank=True)
    error = models.CharField(max_length=128, blank=True)
    job_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
