import logging
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory
from redis.exceptions import ConnectionError as RedisConnectionError

from accounts.logging import RedactTokenPaths
from accounts.management.commands import retry_jobs
from accounts.models import EmailJob
from accounts.services import schedule_email
from accounts.throttles import ResilientAnonThrottle

from .helpers import ApiCase
from .test_videos import create_video


class RecoveryTests(ApiCase):
    def test_retry_pending_and_failed_durable_jobs(self):
        create_video(status="failed")
        schedule_email(self.user, "reset")
        with patch.object(retry_jobs, "enqueue_video") as queued_video:
            with patch.object(retry_jobs, "enqueue_email") as queued_email:
                call_command("retry_jobs")
        self.assertEqual(queued_video.call_count, 1)
        self.assertEqual(queued_email.call_count, 1)

    def test_recover_requires_explicit_video(self):
        with self.assertRaises(CommandError):
            call_command("retry_jobs", recover_stopped=True)

    def test_recovery_of_stopped_processing_job(self):
        video = create_video(status="processing")
        with patch(
            "accounts.management.commands.retry_jobs.enqueue_video"
        ) as job:
            call_command("retry_jobs", video_id=video.pk, recover_stopped=True)
        video.refresh_from_db()
        self.assertEqual(video.status, "failed")
        job.assert_called_once_with(video.pk)

    def test_successful_jobs_not_retried(self):
        create_video(status="ready")
        schedule_email(self.user, "reset")
        EmailJob.objects.update(status="sent")
        with patch.object(retry_jobs, "enqueue_video") as queued_video:
            with patch.object(retry_jobs, "enqueue_email") as queued_email:
                call_command("retry_jobs")
        queued_video.assert_not_called()
        queued_email.assert_not_called()


class InfrastructureFailureTests(ApiCase):
    def test_throttle_redis_failure_is_logged(self):
        request = RequestFactory().get("/api/login/")
        request.user = type("Anonymous", (), {"is_authenticated": False})()
        throttle = ResilientAnonThrottle()
        with patch.object(
            throttle.cache, "get", side_effect=RedisConnectionError
        ):
            with self.assertLogs("accounts.throttles", level="ERROR"):
                self.assertTrue(throttle.allow_request(request, None))

    def test_throttle_normal_request(self):
        request = RequestFactory().get("/api/login/")
        request.user = type("Anonymous", (), {"is_authenticated": False})()
        self.assertTrue(ResilientAnonThrottle().allow_request(request, None))

    def test_token_paths_redacted_from_logs(self):
        record = logging.LogRecord(
            "django.request",
            logging.WARNING,
            "",
            1,
            "Bad Request: %s",
            ("/api/password_confirm/uid/token/",),
            None,
        )
        self.assertTrue(RedactTokenPaths().filter(record))
        expected = "Bad Request: /api/password_confirm/[redacted]/"
        self.assertEqual(record.getMessage(), expected)
