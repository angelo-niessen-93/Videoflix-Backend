import json
import shutil
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.core.files import File
from django.test import tag
from rest_framework.test import APIClient

from videos.ffmpeg import playlist_segments, probe_video, run_process
from videos.models import Video
from videos.paths import video_root
from videos.tasks import convert_video

from .helpers import ApiCase, login_cookies

DECODE_INPUT_FLAGS = ["-v", "error", "-nostdin"]
DECODE_OUTPUT_FLAGS = ["-f", "null", "-"]
SOURCE_FLAGS = [
    "-v",
    "error",
    "-y",
    "-f",
    "lavfi",
    "-i",
    "testsrc2=size=1920x1080:rate=24",
    "-f",
    "lavfi",
    "-i",
    "sine=frequency=440:sample_rate=44100",
    "-t",
    "1.2",
    "-c:v",
    "libx264",
    "-preset",
    "ultrafast",
    "-threads",
    "2",
    "-pix_fmt",
    "yuv420p",
    "-c:a",
    "aac",
]
AUDIO_PROBE_FLAGS = [
    "-v",
    "error",
    "-select_streams",
    "a:0",
    "-show_entries",
    "stream=codec_name",
    "-of",
    "json",
]


def manifest_references(response):
    return [
        line
        for line in response.content.decode().splitlines()
        if line and not line.startswith("#")
    ]


def assert_segment(client, path):
    response = client.get(path)
    try:
        assert response.status_code == 200
        assert b"".join(response.streaming_content)[0] == 0x47
    finally:
        response.close()


def generate_source(destination: Path):
    arguments = [settings.FFMPEG_BINARY, *SOURCE_FLAGS, str(destination)]
    run_process(arguments, 60)


def source_video(source: Path):
    with source.open("rb") as handle:
        return Video.objects.create(
            title="Integration clip",
            description="FFmpeg test",
            category="Test",
            upload=File(handle, name="source.mp4"),
        )


@tag("ffmpeg")
@skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required for real media integration",
)
class FfmpegTests(ApiCase):
    @classmethod
    def setUpTestData(cls):
        source = Path(settings.PRIVATE_MEDIA_ROOT) / "integration-source.mp4"
        source.parent.mkdir(parents=True, exist_ok=True)
        generate_source(source)
        cls.video = source_video(source)
        convert_video(cls.video.pk)
        cls.video.refresh_from_db()

    def assert_variant(self, resolution):
        folder = video_root(self.video.pk) / resolution
        segments = playlist_segments(folder)
        self.assertTrue(segments)
        for segment in segments:
            metadata = probe_video(folder / segment)
            self.assertEqual(metadata["height"], int(resolution[:-1]))
            self.assertEqual(metadata["codec_name"], "h264")
            self.assertEqual((folder / segment).read_bytes()[0], 0x47)

    def test_real_480p(self):
        self.assert_variant("480p")

    def test_real_720p(self):
        self.assert_variant("720p")

    def test_real_1080p(self):
        self.assert_variant("1080p")

    def test_status_thumbnail_original_and_resolutions(self):
        self.assertEqual(self.video.status, "ready")
        self.assertEqual(self.video.resolutions, ["480p", "720p", "1080p"])
        self.assertTrue(Path(self.video.thumbnail.path).is_file())
        self.assertTrue(Path(self.video.upload.path).is_file())
        from PIL import Image

        with Image.open(self.video.thumbnail.path) as thumbnail:
            thumbnail.verify()

    def test_real_manifest_segment_references_over_api(self):
        client = APIClient()
        login_cookies(client, self.user)
        for resolution in self.video.resolutions:
            base = f"/api/video/{self.video.pk}/{resolution}/"
            response = client.get(base + "index.m3u8")
            self.assertEqual(response.status_code, 200)
            for reference in manifest_references(response):
                assert_segment(client, base + reference)

    def test_real_audio_codec(self):
        segment = video_root(self.video.pk) / "480p/000.ts"
        result = run_process(
            [settings.FFPROBE_BINARY, *AUDIO_PROBE_FLAGS, str(segment)], 30
        )
        streams = json.loads(result.stdout)["streams"]
        self.assertEqual(streams[0]["codec_name"], "aac")

    def test_real_invalid_source_failure_retains_original(self):
        invalid = Path(settings.PRIVATE_MEDIA_ROOT) / "invalid.mp4"
        invalid.write_bytes(b"invalid media")
        video = source_video(invalid)
        import subprocess

        with self.assertRaises(subprocess.CalledProcessError):
            convert_video(video.pk)
        video.refresh_from_db()
        self.assertEqual(video.status, "failed")
        self.assertTrue(Path(video.upload.path).is_file())

    def test_playlists_decode_successfully(self):
        for resolution in self.video.resolutions:
            manifest = video_root(self.video.pk) / resolution / "index.m3u8"
            arguments = [
                settings.FFMPEG_BINARY,
                *DECODE_INPUT_FLAGS,
                "-i",
                str(manifest),
                *DECODE_OUTPUT_FLAGS,
            ]
            result = run_process(arguments, 30)
            self.assertEqual(result.stderr, "")

    def test_retry_reuses_valid_variants(self):
        Video.objects.filter(pk=self.video.pk).update(status="failed")
        with patch("videos.services.convert_variant") as conversion:
            convert_video(self.video.pk)
        conversion.assert_not_called()
        self.video.refresh_from_db()
        self.assertEqual(self.video.status, "ready")
