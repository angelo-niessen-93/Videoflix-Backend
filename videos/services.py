from pathlib import Path

from django.core.files import File
from django.db import transaction
from PIL import Image

from .ffmpeg import (
    complete_variant,
    convert_variant,
    create_thumbnail,
    probe_video,
    target_resolutions,
    validate_variant,
)
from .models import Video
from .paths import video_root


@transaction.atomic
def claim_video(video_id: int):
    video = Video.objects.select_for_update().get(pk=video_id)
    if video.status in (Video.Status.READY, Video.Status.PROCESSING):
        return None
    video.status = Video.Status.PROCESSING
    video.error = ""
    video.save(update_fields=["status", "error"])
    return video


def build_variants(source: Path, root: Path, resolutions: list[str]):
    for resolution in resolutions:
        folder = root / resolution
        height = int(resolution[:-1])
        if not complete_variant(folder, height):
            convert_variant(source, folder, height)
        validate_variant(folder, height)


def publish_video(video, thumbnail: Path, resolutions: list[str]):
    with Image.open(thumbnail) as image:
        image.verify()
    with thumbnail.open("rb") as handle:
        video.thumbnail.save(f"{video.pk}.jpg", File(handle), save=False)
    video.resolutions = resolutions
    video.status = Video.Status.READY
    video.error = ""
    video.save(update_fields=["thumbnail", "resolutions", "status", "error"])


def process_video(video):
    source = Path(video.upload.path)
    metadata = probe_video(source)
    resolutions = target_resolutions(metadata["height"])
    if not resolutions:
        raise ValueError("Source below minimum supported height of 480 pixels")
    root = video_root(video.pk)
    root.mkdir(parents=True, exist_ok=True)
    build_variants(source, root, resolutions)
    thumbnail = root / "thumbnail.jpg"
    create_thumbnail(source, thumbnail)
    publish_video(video, thumbnail, resolutions)
