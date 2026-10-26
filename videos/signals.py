from functools import partial

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Video
from .tasks import enqueue_video


@receiver(post_save, sender=Video)
def schedule_video(sender, instance, created, raw=False, **kwargs):
    if created and not raw and instance.upload:
        transaction.on_commit(partial(enqueue_video, instance.pk))
