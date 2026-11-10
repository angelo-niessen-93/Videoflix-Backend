import logging

from django.core.cache import cache
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def read_playlist(path) -> str:
    """Cache playlist reads and tolerate Redis outages."""
    key = f"playlist:{path}:{path.stat().st_mtime_ns}"
    try:
        value = cache.get(key)
        if value is None:
            value = path.read_text(encoding="utf-8")
            cache.set(key, value, timeout=30)
        return value
    except RedisError:
        logger.warning("Playlist cache unavailable")
        return path.read_text(encoding="utf-8")


def playlist_response_text(path) -> str:
    """Add API trailing slashes to HLS segment references."""
    lines = read_playlist(path).splitlines()
    return (
        "\n".join(
            line + "/" if line and not line.startswith("#") else line
            for line in lines
        )
        + "\n"
    )
