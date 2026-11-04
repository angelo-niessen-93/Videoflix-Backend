"""Opt-in live acceptance on a disposable database, never production."""

import secrets
import subprocess
import tempfile
import time
from pathlib import Path

import django_rq
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client
from rq import Worker

from accounts.models import EmailJob, User
from accounts.services import schedule_email
from videos.models import Video
from videos.paths import RESOLUTIONS, video_root

SOURCE_FLAGS = (
    "-v error -nostdin -y -f lavfi -i testsrc2=size=1920x1080:rate=24 "
    "-f lavfi -i sine=frequency=440:sample_rate=44100 -t 1.2 "
    "-c:v libx264 -preset ultrafast -threads 2 -pix_fmt yuv420p -c:a aac"
).split()


def require(condition, message):
    if not condition:
        raise CommandError(message)


def verify_isolation():
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
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        instance.refresh_from_db()
        if instance.status == status:
            return
        require(instance.status != "failed", "Worker reported task failure")
        time.sleep(0.5)
    raise CommandError(f"Worker did not reach {status} before timeout")


def verify_email(user):
    existing = set(Path(settings.EMAIL_FILE_PATH).glob("*.log"))
    schedule_email(user, "reset")
    job = EmailJob.objects.filter(user=user).latest("pk")
    wait_for_status(job, "sent")
    files = set(Path(settings.EMAIL_FILE_PATH).glob("*.log")) - existing
    require(bool(files), "Email worker did not write a local test message")
    require(bool(job.job_id), "Email has no real RQ job ID")


def generate_video(destination):
    subprocess.run(
        [settings.FFMPEG_BINARY, *SOURCE_FLAGS, str(destination)],
        check=True,
        timeout=60,
        capture_output=True,
    )


def upload_video(client, identifier):
    with tempfile.TemporaryDirectory(prefix="videoflix-acceptance-") as root:
        source = Path(root) / "synthetic.mp4"
        generate_video(source)
        data = dict(title=identifier, description="Synthetic", category="QA")
        data["upload"] = SimpleUploadedFile(source.name, source.read_bytes())
        response = client.post("/admin/videos/video/add/", data)
    require(response.status_code == 302, "Real admin upload failed")
    return Video.objects.get(title=identifier)


def verify_stream(client, video, resolution):
    base = f"/api/video/{video.pk}/{resolution}/"
    manifest = client.get(base + "index.m3u8")
    require(manifest.status_code == 200, "Authenticated manifest failed")
    lines = manifest.content.decode().splitlines()
    segments = [line for line in lines if line and not line.startswith("#")]
    require(bool(segments), "Empty HLS manifest")
    for segment in segments:
        response = client.get(base + segment)
        require(response.status_code == 200, "Authenticated segment failed")
        try:
            require(b"".join(response.streaming_content)[0] == 0x47, "Bad TS")
        finally:
            response.close()


def verify_video(client, video):
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
    manifest = video_root(video.pk) / resolution / "index.m3u8"
    arguments = [settings.FFMPEG_BINARY, "-v", "error", "-nostdin", "-i"]
    subprocess.run(
        [*arguments, str(manifest), "-f", "null", "-"],
        check=True,
        timeout=60,
        capture_output=True,
    )


def authenticated_client(user, password):
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
    verify_isolation()
    verify_redis()
    identifier, password = secrets.token_hex(12), secrets.token_urlsafe(32)
    user = User.objects.create_superuser(
        identifier, identifier + "@example.invalid", password
    )
    verify_email(user)
    client = authenticated_client(user, password)
    client.force_login(user)
    video = upload_video(client, identifier)
    verify_video(client, video)
    print("PASS: PostgreSQL, Redis, RQ, email, admin and HLS")
