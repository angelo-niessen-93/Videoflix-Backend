import re
from pathlib import Path

from django.conf import settings
from django.http import Http404

RESOLUTIONS = ("480p", "720p", "1080p")
SEGMENT_PATTERN = re.compile(r"[0-9]{3,8}\.ts\Z")


def video_root(video_id: int) -> Path:
    return Path(settings.PRIVATE_MEDIA_ROOT) / "videos" / str(video_id)


def safe_segment(name: str) -> bool:
    return SEGMENT_PATTERN.fullmatch(name) is not None


def protected_file(video, resolution: str, filename: str) -> Path:
    if resolution not in RESOLUTIONS or resolution not in video.resolutions:
        raise Http404
    if filename != "index.m3u8" and not safe_segment(filename):
        raise Http404
    root = video_root(video.pk).resolve()
    file_path = (root / resolution / filename).resolve()
    if not file_path.is_relative_to(root) or not file_path.is_file():
        raise Http404
    return file_path
