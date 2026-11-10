"""Verify staff email login and thumbnail changes through admin forms."""

import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings, tag
from PIL import Image
from redis.exceptions import ConnectionError as RedisConnectionError
from rq.job import JobStatus

from accounts.models import User
from videos.admin import VideoAdmin
from videos.ffmpeg import run_process
from videos.models import Video
from videos.paths import video_root
from videos.services import publish_video
from videos.tasks import convert_video
from videos.thumbnails import delete_unreferenced, repair_thumbnail

from .helpers import (
    PASSWORD,
    ApiCase,
    close_response,
    login_cookies,
    streamed_bytes,
)
from .test_ffmpeg import SOURCE_FLAGS


def image_upload(color="red"):
    """Create a PNG upload for byte comparisons after video processing."""
    buffer = BytesIO()
    Image.new("RGB", (64, 36), color).save(buffer, format="PNG")
    return SimpleUploadedFile("custom.png", buffer.getvalue(), "image/png")


def media_snapshot(video):
    """Hash source and HLS files to detect destructive thumbnail edits."""
    paths = [Path(video.upload.path), *video_root(video.pk).rglob("*.ts")]
    paths += list(video_root(video.pk).rglob("*.m3u8"))
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


class AdminLoginTests(TestCase):
    """Verify staff email sessions preserve account identities."""

    def setUp(self):
        """Create a superuser with a separate internal username."""
        self.user = User.objects.create_superuser(
            "internal-admin", "admin@example.com", PASSWORD
        )

    def test_label_and_email_widget(self):
        """Display the actual login identifier without a template override."""
        response = self.client.get("/admin/login/")
        field = response.context["form"].fields["username"]
        self.assertEqual(field.label, "Email address")
        self.assertEqual(field.widget.input_type, "email")
        self.assertContains(response, "Videoflix administration")

    def test_invalid_login_message_names_email(self):
        """Explain rejected staff credentials using the email identifier."""
        response = self.client.post(
            "/admin/login/",
            {"username": self.user.email, "password": "incorrect-password"},
        )
        self.assertContains(response, "correct email address and password")
        self.assertNotContains(response, "correct username and password")

    def test_superuser_email_login_preserves_account(self):
        """Keep password and identity intact during email authentication."""
        original = self.user.password
        data = {"username": "ADMIN@example.com", "password": PASSWORD}
        response = self.client.post(
            "/admin/login/", {**data, "next": "/admin/"}
        )
        self.assertRedirects(response, "/admin/")
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, original)
        self.assertEqual(self.user.username, "internal-admin")
        self.assertEqual(User.objects.count(), 1)

    def test_nonstaff_cannot_login(self):
        """Reject valid credentials for accounts without staff privileges."""
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        response = self.client.post(
            "/admin/login/",
            {"username": self.user.email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_rq_status_tolerates_queue_outage(self):
        """Keep admin video details usable while Redis is unavailable."""
        video = Video(job_id="test-job", status="ready")
        model_admin = VideoAdmin(Video, admin.site)
        with patch(
            "videos.admin.django_rq.get_queue",
            side_effect=RedisConnectionError,
        ):
            self.assertEqual(
                model_admin.rq_job_status(video), "Queue unavailable"
            )
        self.assertEqual(video.status, "ready")

    def test_rq_status_distinguishes_expired_and_finished_jobs(self):
        """Distinguish expired job records from finished queue jobs."""
        video = Video(job_id="test-job")
        model_admin = VideoAdmin(Video, admin.site)
        with patch("videos.admin.django_rq.get_queue") as queue:
            queue.return_value.fetch_job.return_value = None
            self.assertEqual(
                model_admin.rq_job_status(video), "Job expired or missing"
            )
            job = queue.return_value
            job.fetch_job.return_value = job
            job.get_status.return_value = JobStatus.FINISHED
            self.assertEqual(model_admin.rq_job_status(video), "finished")


@tag("ffmpeg")
class ThumbnailAdminTests(ApiCase):
    """Process sources and edit thumbnails through actual admin forms."""

    @classmethod
    def setUpTestData(cls):
        """Generate a short 480p video once for real lifecycle tests."""
        cls.source = Path(settings.PRIVATE_MEDIA_ROOT) / "admin-source.mp4"
        cls.source.parent.mkdir(parents=True, exist_ok=True)
        flags = [
            value.replace("1920x1080", "854x480") for value in SOURCE_FLAGS
        ]
        run_process([settings.FFMPEG_BINARY, *flags, str(cls.source)], 60)

    def setUp(self):
        """Authenticate staff and dashboard clients for each isolated test."""
        super().setUp()
        self.isolate_media()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_login(self.user)
        login_cookies(self.client, self.user)

    def isolate_media(self):
        """Isolate media when database primary keys are reused across tests."""
        directory = TemporaryDirectory(prefix="videoflix-test-admin-")
        root = Path(self.enterContext(directory))
        self.enterContext(
            override_settings(
                MEDIA_ROOT=root / "public", PRIVATE_MEDIA_ROOT=root / "private"
            )
        )

    def add_video(self, custom=True):
        """Upload through an admin form and run real video conversion."""
        data = self.upload_data()
        if custom:
            data["thumbnail"] = image_upload()
        response = self.client.post("/admin/videos/video/add/", data)
        self.assertEqual(response.status_code, 302)
        video = Video.objects.latest("pk")
        convert_video(video.pk)
        video.refresh_from_db()
        return video

    def upload_data(self):
        """Build multipart content from the shared synthetic source fixture."""
        return {
            "title": "Admin film",
            "description": "Real media",
            "category": "Drama",
            "upload": SimpleUploadedFile("film.mp4", self.source.read_bytes()),
        }

    def edit_video(self, video, **changes):
        """Save a real admin change form and execute committed file cleanup."""
        data = {
            "title": video.title,
            "description": video.description,
            "category": video.category,
            **changes,
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/admin/videos/video/{video.pk}/change/", data
            )
        video.refresh_from_db()
        return response

    def assert_visible(self, video):
        """Verify dashboard visibility and decode the public thumbnail."""
        response = self.client.get("/api/video/")
        self.assertIn(video.pk, [item["id"] for item in response.data])
        image = self.client.get(video.thumbnail.url, follow=True)
        self.assertEqual(image.status_code, 200)
        with Image.open(BytesIO(streamed_bytes(image))) as decoded:
            decoded.verify()
        self.assertEqual(video.status, "ready")

    def test_custom_upload_survives_real_conversion(self):
        """Keep the exact uploaded bytes when FFmpeg publishes HLS variants."""
        expected = image_upload().read()
        video = self.add_video()
        self.assertEqual(Path(video.thumbnail.path).read_bytes(), expected)
        self.assertFalse((video_root(video.pk) / "thumbnail.jpg").exists())
        self.assert_visible(video)

    def test_no_custom_upload_generates_thumbnail(self):
        """Publish a generated image when the initial form has no thumbnail."""
        video = self.add_video(custom=False)
        self.assertTrue((video_root(video.pk) / "thumbnail.jpg").exists())
        self.assert_visible(video)

    def test_replacement_preserves_hls_and_removes_old_image(self):
        """Replace a custom image without another video conversion."""
        video = self.add_video()
        before, old = media_snapshot(video), Path(video.thumbnail.path)
        with patch("videos.tasks.enqueue_video") as enqueue:
            response = self.edit_video(video, thumbnail=image_upload("blue"))
        self.assertEqual(response.status_code, 302)
        enqueue.assert_not_called()
        self.assertEqual(media_snapshot(video), before)
        self.assertFalse(old.exists())
        expected = image_upload("blue").read()
        self.assertEqual(Path(video.thumbnail.path).read_bytes(), expected)
        self.assert_visible(video)

    def test_clear_custom_generates_only_thumbnail(self):
        """Restore a source frame after clearing the custom image."""
        video = self.add_video()
        before = media_snapshot(video)
        with patch("videos.services.convert_variant") as conversion:
            response = self.edit_video(video, **{"thumbnail-clear": "on"})
        self.assertEqual(response.status_code, 302)
        conversion.assert_not_called()
        self.assertEqual(media_snapshot(video), before)
        self.assertEqual(Video.objects.count(), 1)
        self.assert_visible(video)

    def test_clear_generated_reuses_private_image(self):
        """Restore a cached source frame without running FFmpeg again."""
        video = self.add_video(custom=False)
        with patch("videos.thumbnails.create_thumbnail") as generate:
            self.edit_video(video, **{"thumbnail-clear": "on"})
        generate.assert_not_called()
        self.assert_visible(video)

    def test_missing_generated_files_regenerate_on_image_request(self):
        """Regenerate deleted public and cached images on HTTP access."""
        video = self.add_video(custom=False)
        before, url = media_snapshot(video), video.thumbnail.url
        Path(video.thumbnail.path).unlink()
        (video_root(video.pk) / "thumbnail.jpg").unlink()
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        close_response(response)
        video.refresh_from_db()
        self.assertEqual(media_snapshot(video), before)
        self.assert_visible(video)

    def test_clear_failure_uses_safe_fallback(self):
        """Keep the video ready and listed when extracting a frame fails."""
        video = self.add_video()
        with patch("videos.thumbnails.create_thumbnail", side_effect=OSError):
            with self.assertLogs("videos.thumbnails", level="ERROR"):
                self.edit_video(video, **{"thumbnail-clear": "on"})
        self.assertTrue((video_root(video.pk) / "fallback.jpg").exists())
        self.assertEqual(video.error, "")
        self.assert_visible(video)

    def test_invalid_image_rejected_by_admin(self):
        """Reject disguised image files without changing video media."""
        video = self.add_video()
        old = video.thumbnail.name
        invalid = SimpleUploadedFile("fake.png", b"not an image", "image/png")
        response = self.edit_video(video, thumbnail=invalid)
        self.assertEqual(response.status_code, 200)
        self.assertIn("thumbnail", response.context["adminform"].form.errors)
        self.assertEqual(video.thumbnail.name, old)
        self.assert_visible(video)

    def test_stale_worker_preserves_new_custom_thumbnail(self):
        """Preserve the latest thumbnail when a stale worker publishes."""
        video = self.add_video()
        stale = Video.objects.get(pk=video.pk)
        self.edit_video(video, thumbnail=image_upload("blue"))
        name = video.thumbnail.name
        publish_video(stale, ["480p"])
        video.refresh_from_db()
        self.assertEqual(video.thumbnail.name, name)
        self.assert_visible(video)

    def test_stale_admin_preserves_worker_status(self):
        """Retain worker results when a stale admin form is submitted."""
        video = self.add_video()
        stale = Video.objects.get(pk=video.pk)
        stale.status, stale.resolutions = "processing", []
        model_admin = VideoAdmin(Video, admin.site)
        model_admin.save_model(RequestFactory().post("/"), stale, None, True)
        video.refresh_from_db()
        self.assertEqual(video.resolutions, ["480p"])
        self.assert_visible(video)

    def test_field_delete_restores_image_and_keeps_video(self):
        """Restore ImageField deletion while retaining the source."""
        video = self.add_video()
        before = media_snapshot(video)
        video.thumbnail.delete()
        video.refresh_from_db()
        self.assertEqual(media_snapshot(video), before)
        self.assert_visible(video)

    def test_repair_preserves_existing_custom_file(self):
        """Avoid new files when a valid custom thumbnail already exists."""
        video = self.add_video()
        name = video.thumbnail.name
        self.assertEqual(repair_thumbnail(video.pk).thumbnail.name, name)

    def test_cleanup_retains_shared_reference(self):
        """Never delete a thumbnail still referenced by another video."""
        video = self.add_video()
        delete_unreferenced(video.thumbnail.storage, video.thumbnail.name)
        self.assertTrue(Path(video.thumbnail.path).exists())

    def test_labels_and_original_readonly(self):
        """Expose clear labels and protect the original video source."""
        video = self.add_video()
        response = self.client.get(f"/admin/videos/video/{video.pk}/change/")
        self.assertContains(response, "Processing status")
        self.assertContains(response, "RQ job ID")
        form = response.context["adminform"].form
        self.assertEqual(form.fields["thumbnail"].label, "Thumbnail image")
        self.assertNotIn("upload", form.fields)
