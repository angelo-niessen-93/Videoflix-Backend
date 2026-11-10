from functools import partial

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Video
from .tasks import enqueue_video
from .thumbnails import repair_thumbnail


@receiver(post_save, sender=Video)
def schedule_video(sender, instance, created, raw=False, **kwargs):
    """Queue new video processing after the transaction commits."""
    if created and not raw and instance.upload:
        transaction.on_commit(partial(enqueue_video, instance.pk))


@receiver(post_save, sender=Video)
def recover_cleared_thumbnail(sender, instance, created, raw=False, **kwargs):
    """Restore cleared images for playable videos with an original source."""
    if raw or created or instance.thumbnail or not instance.upload:
        return
    if instance.status == Video.Status.READY:
        restored = repair_thumbnail(instance.pk)
        instance.thumbnail = restored.thumbnail.name
