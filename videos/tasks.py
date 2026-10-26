import logging

from redis.exceptions import RedisError

from config.jobs import queue_task

from .models import Video
from .services import claim_video, process_video

logger = logging.getLogger(__name__)


def enqueue_video(video_id: int):
    try:
        job = queue_task("video", convert_video, video_id, 7200, 2)
        Video.objects.filter(pk=video_id).update(job_id=job.id)
    except RedisError as error:
        Video.objects.filter(pk=video_id).update(
            status=Video.Status.FAILED, error=type(error).__name__
        )
        logger.error("Video queue unavailable; video %s retained", video_id)


def convert_video(video_id: int):
    video = claim_video(video_id)
    if video is None:
        return
    try:
        process_video(video)
    except Exception as error:
        Video.objects.filter(pk=video_id).update(
            status=Video.Status.FAILED, error=type(error).__name__
        )
        logger.error("Video %s failed (%s)", video_id, type(error).__name__)
        raise
