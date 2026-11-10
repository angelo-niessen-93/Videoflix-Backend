from django.core.management.base import BaseCommand, CommandError

from accounts.models import EmailJob
from accounts.tasks import enqueue_email
from videos.models import Video
from videos.tasks import enqueue_video


class Command(BaseCommand):
    """Retry durable jobs or explicitly recover a stopped conversion."""

    help = "Retry durable pending/failed jobs, or recover a stopped video."

    def add_arguments(self, parser):
        """Expose video selection and explicit stopped-worker recovery."""
        parser.add_argument("--video-id", type=int)
        parser.add_argument("--recover-stopped", action="store_true")

    def handle(self, *args, **options):
        """Retry work with explicit authorization for stopped conversions."""
        video_id = options["video_id"]
        if options["recover_stopped"]:
            self.recover_video(video_id)
        videos = Video.objects.filter(status__in=["pending", "failed"])
        if video_id:
            videos = videos.filter(pk=video_id)
        for video in videos:
            enqueue_video(video.pk)
        self.retry_emails()

    def retry_emails(self):
        """Requeue durable email jobs that have not completed successfully."""
        for job in EmailJob.objects.filter(status__in=["pending", "failed"]):
            enqueue_email(job.pk)

    def recover_video(self, video_id):
        """Release a stopped conversion explicitly selected by the operator."""
        if not video_id:
            raise CommandError("Recovery requires --video-id.")
        Video.objects.filter(pk=video_id, status="processing").update(
            status="failed", error="OperatorRecoveredStoppedJob"
        )
