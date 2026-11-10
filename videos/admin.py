from functools import partial

import django_rq
from django import forms
from django.contrib import admin
from django.db import transaction
from redis.exceptions import RedisError

from .models import Video
from .thumbnails import delete_unreferenced, restore_thumbnail

PROCESSING_FIELDS = ("status", "resolutions", "error", "job_id")


class VideoAdminForm(forms.ModelForm):
    """Validate uploaded images and provide consistent content labels."""

    class Meta:
        model = Video
        fields = "__all__"
        labels = {"title": "Video title", "thumbnail": "Thumbnail image"}
        help_texts = {
            "thumbnail": "Optional image. Clear to restore a video frame."
        }


def retain_processing_fields(obj, previous):
    """Preserve processing values when an admin submits a stale form."""
    for field in PROCESSING_FIELDS:
        setattr(obj, field, getattr(previous, field))


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    """Manage video uploads without exposing processing fields for editing."""

    form = VideoAdminForm
    list_display = (
        "title",
        "category",
        "status",
        "rq_job_status",
        "created_at",
    )
    list_filter = ("status", "category")
    readonly_fields = (*PROCESSING_FIELDS, "rq_job_status")

    @admin.display(description="RQ job status")
    def rq_job_status(self, obj):
        """Show RQ state while tolerating Redis outages."""
        if not obj.job_id:
            return "Not queued"
        try:
            job = django_rq.get_queue("video").fetch_job(obj.job_id)
            return job.get_status() if job else "Job expired or missing"
        except RedisError:
            return "Queue unavailable"

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        """Lock edits against publication and repair cleared thumbnails."""
        old = locked_previous(obj) if change else None
        if old:
            retain_processing_fields(obj, old)
        super().save_model(request, obj, form, change)
        if obj.status == Video.Status.READY:
            restore_thumbnail(obj)
        if old and old.thumbnail.name != obj.thumbnail.name:
            retire_thumbnail(old)

    def get_readonly_fields(self, request, obj=None):
        """Prevent replacing an existing video source through the admin."""
        fields = super().get_readonly_fields(request, obj)
        return (*fields, "upload") if obj else fields


def locked_previous(video):
    """Lock the stored video before applying an admin update."""
    return Video.objects.select_for_update().get(pk=video.pk)


def retire_thumbnail(video):
    """Delete the replaced image only after the admin transaction commits."""
    transaction.on_commit(
        partial(
            delete_unreferenced, video.thumbnail.storage, video.thumbnail.name
        )
    )
