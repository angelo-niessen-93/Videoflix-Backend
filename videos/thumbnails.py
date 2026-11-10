"""Restore thumbnails independently of video conversion and HLS storage."""

import logging
from functools import partial
from pathlib import Path
from subprocess import SubprocessError
from uuid import uuid4

from django.core.files import File
from django.db import transaction
from PIL import Image

from .ffmpeg import create_thumbnail
from .models import Video
from .paths import video_root

logger = logging.getLogger(__name__)


def valid_image(path):
    """Return whether a local file contains a decodable image."""
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def generated_thumbnail(video):
    """Reuse the private generated image or regenerate it from the source."""
    root = thumbnail_directory(video.pk)
    destination = root / "thumbnail.jpg"
    if not valid_image(destination):
        temporary = root / f"thumbnail-{uuid4().hex}.jpg"
        try:
            create_thumbnail(Path(video.upload.path), temporary)
            if not valid_image(temporary):
                raise ValueError("Invalid generated thumbnail")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination


def fallback_thumbnail(video):
    """Create a neutral image without marking video conversion as failed."""
    destination = video_root(video.pk) / "fallback.jpg"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not valid_image(destination):
        Image.new("RGB", (640, 360), "#172033").save(destination)
    return destination


def thumbnail_source(video):
    """Use a generated image, logging recoverable failures before fallback."""
    try:
        return generated_thumbnail(video)
    except (OSError, ValueError, SubprocessError):
        logger.exception("Thumbnail recovery deferred for video %s", video.pk)
        return fallback_thumbnail(video)


def delete_unreferenced(storage, name):
    """Delete a public thumbnail only after its last reference ends."""
    if name and not Video.objects.filter(thumbnail=name).exists():
        storage.delete(name)


def replace_thumbnail(video, source):
    """Store a unique public image and retire its predecessor after commit."""
    old = video.thumbnail.name
    with source.open("rb") as handle:
        video.thumbnail.save(
            f"{video.pk}-{uuid4().hex}.jpg", File(handle), False
        )
    Video.objects.filter(pk=video.pk).update(thumbnail=video.thumbnail.name)
    transaction.on_commit(
        partial(delete_unreferenced, video.thumbnail.storage, old)
    )


def restore_thumbnail(video):
    """Restore a missing image while preserving any current custom upload."""
    if video.thumbnail and video.thumbnail.storage.exists(
        video.thumbnail.name
    ):
        return
    replace_thumbnail(video, thumbnail_source(video))


@transaction.atomic
def repair_thumbnail(video_id):
    """Serialize thumbnail repair with admin edits and worker publication."""
    video = Video.objects.select_for_update().get(pk=video_id)
    restore_thumbnail(video)
    return video


def thumbnail_directory(video_id):
    """Create and return the video's private thumbnail cache directory."""
    root = video_root(video_id)
    root.mkdir(parents=True, exist_ok=True)
    return root
