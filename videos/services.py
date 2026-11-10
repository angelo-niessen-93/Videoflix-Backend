from pathlib import Path

from django.db import transaction

from .ffmpeg import (
    complete_variant,
    convert_variant,
    probe_video,
    target_resolutions,
    validate_variant,
)
from .models import Video
from .paths import video_root
from .thumbnails import restore_thumbnail


@transaction.atomic
def claim_video(video_id: int):
    """Lock and claim a pending or failed video for conversion."""
    video = Video.objects.select_for_update().get(pk=video_id)
    if video.status in (Video.Status.READY, Video.Status.PROCESSING):
        return None
    video.status = Video.Status.PROCESSING
    video.error = ""
    video.save(update_fields=["status", "error"])
    return video


def build_variants(source: Path, root: Path, resolutions: list[str]):
    """Reuse verified HLS variants and encode only missing or invalid ones."""
    for resolution in resolutions:
        folder = root / resolution
        height = int(resolution[:-1])
        if not complete_variant(folder, height):
            convert_variant(source, folder, height)
        validate_variant(folder, height)


@transaction.atomic
def publish_video(video, resolutions: list[str]):
    """Publish variants using the latest thumbnail committed by the admin."""
    video = Video.objects.select_for_update().get(pk=video.pk)
    restore_thumbnail(video)
    video.resolutions = resolutions
    video.status = Video.Status.READY
    video.error = ""
    video.save(update_fields=["resolutions", "status", "error"])


def process_video(video):
    """Validate the source, build supported HLS variants and publish it."""
    source = Path(video.upload.path)
    metadata = probe_video(source)
    resolutions = target_resolutions(metadata["height"])
    if not resolutions:
        raise ValueError("Source below minimum supported height of 480 pixels")
    root = video_root(video.pk)
    root.mkdir(parents=True, exist_ok=True)
    build_variants(source, root, resolutions)
    publish_video(video, resolutions)
