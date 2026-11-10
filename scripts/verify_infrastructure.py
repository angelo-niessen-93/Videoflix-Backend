"""Opt-in live acceptance on a disposable database, never production."""

import secrets
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import closing
from pathlib import Path
from threading import Event

import django_rq
from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import CommandError
from django.db import close_old_connections, connection, transaction
from django.test import Client
from rq import Worker

from accounts.models import EmailJob, User
from accounts.services import schedule_email
from videos.models import Video
from videos.paths import RESOLUTIONS, video_root
from videos.services import publish_video

SOURCE_FLAGS = (
    "-v error -nostdin -y -f lavfi -i testsrc2=size=1920x1080:rate=24 "
    "-f lavfi -i sine=frequency=440:sample_rate=44100 -t 1.2 "
    "-c:v libx264 -preset ultrafast -threads 2 -pix_fmt yuv420p -c:a aac"
).split()


def require(condition, message):
    """Raise a management error when an acceptance assertion fails."""
    if not condition:
        raise CommandError(message)


def verify_isolation():
    """Reject acceptance runs outside the disposable database setup."""
    require(connection.vendor == "postgresql", "Real PostgreSQL required")
    require(
        connection.settings_dict["NAME"].endswith("_acceptance"),
        "Database name must end in _acceptance; use a disposable stack",
    )
    require(
        settings.EMAIL_BACKEND
        == "django.core.mail.backends.filebased.EmailBackend",
        "File-based local email backend required; SMTP is forbidden",
    )


def verify_redis():
    """Check real Redis queues, registered workers and cache roundtrips."""
    redis = django_rq.get_connection("default")
    require(redis.ping(), "Redis PING failed")
    key = "acceptance:" + secrets.token_hex(12)
    cache.set(key, "verified", timeout=30)
    require(cache.get(key) == "verified", "Real Redis cache roundtrip failed")
    cache.delete(key)
    workers = Worker.all(connection=redis)
    for queue in ("default", "video"):
        require(
            any(queue in worker.queue_names() for worker in workers),
            f"No registered worker for {queue}",
        )


def wait_for_status(instance, status, timeout=180):
    """Wait for worker completion while rejecting failures or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        instance.refresh_from_db()
        if instance.status == status:
            return
        require(instance.status != "failed", "Worker reported task failure")
        time.sleep(0.5)
    raise CommandError(f"Worker did not reach {status} before timeout")


def verify_email(user):
    """Verify an independent worker writes a durable local email."""
    existing = set(Path(settings.EMAIL_FILE_PATH).glob("*.log"))
    schedule_email(user, "reset")
    job = EmailJob.objects.filter(user=user).latest("pk")
    wait_for_status(job, "sent")
    files = set(Path(settings.EMAIL_FILE_PATH).glob("*.log")) - existing
    require(bool(files), "Email worker did not write a local test message")
    require(bool(job.job_id), "Email has no real RQ job ID")


def generate_video(destination):
    """Generate a synthetic audiovisual source for live acceptance."""
    subprocess.run(
        [settings.FFMPEG_BINARY, *SOURCE_FLAGS, str(destination)],
        check=True,
        timeout=60,
        capture_output=True,
    )


def upload_video(client, identifier, thumbnail=None):
    """Upload a synthetic source through the authenticated admin form."""
    with tempfile.TemporaryDirectory(prefix="videoflix-acceptance-") as root:
        source = Path(root) / "synthetic.mp4"
        generate_video(source)
        data = dict(title=identifier, description="Synthetic", category="QA")
        data["upload"] = SimpleUploadedFile(source.name, source.read_bytes())
        if thumbnail:
            data["thumbnail"] = thumbnail
        response = client.post("/admin/videos/video/add/", data)
    require(response.status_code == 302, "Real admin upload failed")
    return Video.objects.get(title=identifier)


def verify_stream(client, video, resolution):
    """Fetch a protected playlist and validate its HTTP segment bytes."""
    base = f"/api/video/{video.pk}/{resolution}/"
    manifest = client.get(base + "index.m3u8")
    require(manifest.status_code == 200, "Authenticated manifest failed")
    lines = manifest.content.decode().splitlines()
    segments = [line for line in lines if line and not line.startswith("#")]
    require(bool(segments), "Empty HLS manifest")
    for segment in segments:
        response = client.get(base + segment)
        require(response.status_code == 200, "Authenticated segment failed")
        with closing(response):
            require(b"".join(response.streaming_content)[0] == 0x47, "Bad TS")


def verify_video(client, video):
    """Upload, process and verify a video using independent workers."""
    wait_for_status(video, "ready")
    require(bool(video.job_id), "Video has no real RQ job ID")
    require(set(video.resolutions) == set(RESOLUTIONS), "Missing resolutions")
    require(video.thumbnail.storage.exists(video.thumbnail.name), "No image")
    response = client.get("/api/video/")
    require(
        any(row["id"] == video.pk for row in response.json()), "Not listed"
    )
    for resolution in RESOLUTIONS:
        verify_stream(client, video, resolution)
        decode_variant(video, resolution)


def decode_variant(video, resolution):
    """Decode a generated HLS playlist using real FFmpeg."""
    manifest = video_root(video.pk) / resolution / "index.m3u8"
    arguments = [settings.FFMPEG_BINARY, "-v", "error", "-nostdin", "-i"]
    subprocess.run(
        [*arguments, str(manifest), "-f", "null", "-"],
        check=True,
        timeout=60,
        capture_output=True,
    )


def authenticated_client(user, password):
    """Create a disposable viewer and authenticate API cookies."""
    client = Client(HTTP_HOST="localhost")
    response = client.post(
        "/api/login/",
        {"email": user.email, "password": password},
        content_type="application/json",
        HTTP_ORIGIN=settings.FRONTEND_URL,
    )
    require(response.status_code == 200, "Cookie login failed")
    return client


def main():
    """Run the verification command and report its acceptance result."""
    verify_isolation()
    verify_redis()
    identifier, password = secrets.token_hex(12), secrets.token_urlsafe(32)
    user = acceptance_user(identifier, password)
    verify_email(user)
    client = authenticated_client(user, password)
    client.force_login(user)
    video = upload_video(client, identifier)
    verify_video_lifecycle(client, video)
    print("PASS: PostgreSQL, Redis, RQ, email, admin and HLS")


def publish_in_thread(video, started):
    """Publish stale worker state through a separate PostgreSQL connection."""
    close_old_connections()
    try:
        started.set()
        publish_video(video, video.resolutions)
    finally:
        close_old_connections()


def require_blocked(future, started):
    """Prove worker publication waits for the admin row lock."""
    require(started.wait(5), "Publication thread did not start")
    try:
        future.result(timeout=0.3)
    except TimeoutError:
        return
    raise CommandError("Worker did not wait for the admin row lock")


def save_concurrent_thumbnail(video):
    """Save a custom image through admin while holding the video lock."""
    cached = video_root(video.pk) / "thumbnail.jpg"
    video.thumbnail = ContentFile(cached.read_bytes(), name="concurrent.jpg")
    admin.site._registry[Video].save_model(None, video, None, True)
    return video.thumbnail.name


def verify_thumbnail_concurrency(video):
    """Verify PostgreSQL serializes admin uploads and worker publication."""
    stale, started = Video.objects.get(pk=video.pk), Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.atomic():
            locked = Video.objects.select_for_update().get(pk=video.pk)
            future = executor.submit(publish_in_thread, stale, started)
            require_blocked(future, started)
            name = save_concurrent_thumbnail(locked)
        future.result(timeout=30)
    video.refresh_from_db()
    require(video.thumbnail.name == name, "Worker replaced the custom image")
    require(video.status == "ready", "Publication changed video readiness")
    print("PASS: PostgreSQL thumbnail concurrency")


def acceptance_user(identifier, password):
    """Create a disposable staff identity for infrastructure acceptance."""
    return User.objects.create_superuser(
        identifier, identifier + "@example.invalid", password
    )


def verify_custom_thumbnail_worker(client, reference):
    """Verify RQ conversion preserves the uploaded custom image bytes."""
    expected = (video_root(reference.pk) / "thumbnail.jpg").read_bytes()
    thumbnail = SimpleUploadedFile("custom.jpg", expected, "image/jpeg")
    video = upload_video(client, secrets.token_hex(12), thumbnail)
    verify_video(client, video)
    with video.thumbnail.open("rb") as handle:
        require(
            handle.read() == expected, "Worker replaced custom image bytes"
        )
    generated = video_root(video.pk) / "thumbnail.jpg"
    require(not generated.exists(), "Unneeded extraction")
    print("PASS: custom admin thumbnail preserved by independent RQ worker")


def verify_video_lifecycle(client, video):
    """Check generated images, custom uploads and concurrent publication."""
    verify_video(client, video)
    verify_thumbnail_concurrency(video)
    verify_custom_thumbnail_worker(client, video)
