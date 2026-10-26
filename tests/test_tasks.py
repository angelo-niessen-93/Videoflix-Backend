import subprocess
from unittest.mock import patch

import fakeredis
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from redis.exceptions import ConnectionError as RedisConnectionError
from rq import Queue, SimpleWorker
from rq.timeouts import TimerDeathPenalty

from accounts.models import EmailJob
from accounts.services import schedule_email
from accounts.tasks import enqueue_email, send_account_email
from videos.ffmpeg import target_resolutions
from videos.tasks import convert_video, enqueue_video

from .helpers import ApiCase
from .test_videos import create_video


class PortableWorker(SimpleWorker):
    death_penalty_class = TimerDeathPenalty


class TaskTests(ApiCase):
    def test_registration_enqueues_email_after_commit(self):
        queue = Queue(connection=fakeredis.FakeRedis())
        with patch("config.jobs.django_rq.get_queue", return_value=queue):
            with self.captureOnCommitCallbacks(execute=True):
                schedule_email(self.user, "reset")
        self.assertEqual(queue.count, 1)
        self.assertEqual(
            queue.jobs[0].func_name, "accounts.tasks.send_account_email"
        )

    def test_email_rq_job_executes_with_test_mail_backend(self):
        queue = Queue(connection=fakeredis.FakeRedis())
        schedule_email(self.user, "reset")
        with patch("config.jobs.django_rq.get_queue", return_value=queue):
            enqueue_email(EmailJob.objects.get().pk)
        worker = PortableWorker([queue], connection=queue.connection)
        worker.work(burst=True, logging_level="WARNING")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailJob.objects.get().status, "sent")

    def test_upload_schedules_conversion_after_commit(self):
        queue = Queue("video", connection=fakeredis.FakeRedis())
        upload = SimpleUploadedFile("film.mp4", b"not-real-video")
        with patch("config.jobs.django_rq.get_queue", return_value=queue):
            with self.captureOnCommitCallbacks(execute=True):
                video = create_video(upload=upload, status="pending")
        self.assertEqual(queue.count, 1)
        self.assertEqual(queue.jobs[0].args, (video.pk,))
        self.assertEqual(queue.jobs[0].func_name, "videos.tasks.convert_video")

    def test_queue_outage_preserves_email_job(self):
        schedule_email(self.user, "reset")
        job = EmailJob.objects.get()
        with patch(
            "config.jobs.django_rq.get_queue", side_effect=RedisConnectionError
        ):
            enqueue_email(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error, "ConnectionError")

    def test_queue_outage_preserves_video(self):
        video = create_video(status="pending")
        with patch(
            "config.jobs.django_rq.get_queue", side_effect=RedisConnectionError
        ):
            enqueue_video(video.pk)
        video.refresh_from_db()
        self.assertEqual(video.status, "failed")

    def test_email_failure_is_recorded_and_raised(self):
        schedule_email(self.user, "reset")
        job = EmailJob.objects.get()
        with patch(
            "accounts.tasks.EmailMultiAlternatives.send",
            side_effect=OSError("Mail unavailable"),
        ):
            with self.assertRaises(OSError):
                send_account_email(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error, "OSError")

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_email_not_sent(self):
        schedule_email(self.user, "reset")
        send_account_email(EmailJob.objects.get().pk)
        self.assertEqual(EmailJob.objects.get().status, "expired")
        self.assertEqual(len(mail.outbox), 0)

    def test_failed_ffmpeg_job_not_published(self):
        video = create_video(status="pending")
        error = subprocess.CalledProcessError(1, ["ffmpeg"])
        with patch("videos.tasks.process_video", side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError):
                convert_video(video.pk)
        video.refresh_from_db()
        self.assertEqual(video.status, "failed")
        self.assertEqual(video.error, "CalledProcessError")

    def test_ready_video_is_not_reconverted(self):
        video = create_video()
        with patch("videos.tasks.process_video") as process:
            convert_video(video.pk)
        process.assert_not_called()

    def test_processing_video_is_not_claimed_twice(self):
        video = create_video(status="processing")
        with patch("videos.tasks.process_video") as process:
            convert_video(video.pk)
        process.assert_not_called()

    def test_no_upscaling(self):
        self.assertEqual(target_resolutions(720), ["480p", "720p"])
        self.assertEqual(target_resolutions(1080), ["480p", "720p", "1080p"])
        self.assertEqual(target_resolutions(480), ["480p"])
        self.assertEqual(target_resolutions(360), [])
