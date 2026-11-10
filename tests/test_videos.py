from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import override_settings
from redis.exceptions import ConnectionError as RedisConnectionError

from videos.models import Video
from videos.paths import RESOLUTIONS, video_root

from .helpers import ApiCase, close_response, login_cookies


def create_video(**kwargs):
    """Create dashboard metadata with overridable video test fields."""
    values = {
        "title": "A film",
        "description": "Description",
        "category": "Drama",
        "thumbnail": "thumbnails/test.jpg",
        "status": Video.Status.READY,
        "resolutions": ["480p"],
    }
    return Video.objects.create(**(values | kwargs))


def create_hls_files(video, resolution):
    """Write a minimal playlist and segment for protected-media tests."""
    folder = video_root(video.pk) / resolution
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.m3u8").write_text(
        "#EXTM3U\n#EXTINF:1.0,\n000.ts\n#EXT-X-ENDLIST\n", encoding="utf-8"
    )
    (folder / "000.ts").write_bytes(b"test-segment")
    return folder


UNSAFE_SEGMENTS = (
    "..",
    "..%2F..%2Fsecret",
    "%2e%2e%5csecret",
    "thumbnail.jpg",
    "index.m3u8",
    "secret.txt",
    "000.ts.bak",
)


class VideoListTests(ApiCase):
    """Exercise video list behavior with isolated fixtures."""

    def setUp(self):
        """Prepare isolated fixtures and clients for each test."""
        super().setUp()
        login_cookies(self.client, self.user)

    def test_empty_list_is_array(self):
        """Verify empty list is array."""
        response = self.client.get("/api/video/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_category_thumbnail_and_order(self):
        """Verify category thumbnail and order."""
        first = create_video(title="First")
        second = create_video(title="Second", category="Comedy")
        response = self.client.get("/api/video/")
        self.assertEqual(
            [item["id"] for item in response.data], [second.pk, first.pk]
        )
        self.assertEqual(response.data[0]["category"], "Comedy")
        expected_url = "http://testserver/media/thumbnails/test.jpg"
        self.assertEqual(response.data[0]["thumbnail_url"], expected_url)

    def test_exact_response_fields(self):
        """Verify exact response fields."""
        create_video()
        item = self.client.get("/api/video/").data[0]
        expected = {
            "id",
            "created_at",
            "title",
            "description",
            "category",
            "thumbnail_url",
        }
        self.assertEqual(set(item), expected)

    def test_pending_failed_and_incomplete_videos_hidden(self):
        """Verify pending failed and incomplete videos hidden."""
        for status in ("pending", "processing", "failed"):
            create_video(status=status)
        create_video(thumbnail="")
        create_video(resolutions=[])
        self.assertEqual(self.client.get("/api/video/").data, [])

    def test_list_has_constant_query_count(self):
        """Verify list has constant query count."""
        for _ in range(5):
            create_video()
        with self.assertNumQueries(2):
            self.assertEqual(len(self.client.get("/api/video/").data), 5)


class HlsTests(ApiCase):
    """Exercise hls behavior with isolated fixtures."""

    def setUp(self):
        """Prepare isolated fixtures and clients for each test."""
        super().setUp()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override = override_settings(PRIVATE_MEDIA_ROOT=directory.name)
        override.enable()
        self.addCleanup(override.disable)
        login_cookies(self.client, self.user)
        self.video = create_video(resolutions=list(RESOLUTIONS))
        for resolution in RESOLUTIONS:
            create_hls_files(self.video, resolution)

    def playlist_path(self, resolution="480p"):
        """Build the fixture video playlist endpoint for one resolution."""
        return f"/api/video/{self.video.pk}/{resolution}/index.m3u8"

    def segment_path(self, segment="000.ts", resolution="480p"):
        """Build a protected segment endpoint for the fixture video."""
        return f"/api/video/{self.video.pk}/{resolution}/{segment}/"

    def test_all_resolution_playlists_and_references(self):
        """Verify all resolution playlists and references."""
        for resolution in RESOLUTIONS:
            with self.subTest(resolution=resolution):
                response = self.client.get(self.playlist_path(resolution))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response["Content-Type"], "application/vnd.apple.mpegurl"
                )
                self.assertIn(b"000.ts/", response.content)
                path = self.segment_path("000.ts", resolution)
                segment = self.client.get(path)
                self.assertEqual(segment.status_code, 200)
                close_response(segment)

    def test_segment_content_and_type(self):
        """Verify segment content and type."""
        response = self.client.get(self.segment_path())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "video/MP2T")
        self.assertEqual(b"".join(response.streaming_content), b"test-segment")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        close_response(response)

    def test_invalid_resolution(self):
        """Verify invalid resolution."""
        self.assertEqual(
            self.client.get(self.playlist_path("2160p")).status_code, 404
        )

    def test_invalid_video(self):
        """Verify invalid video."""
        self.assertEqual(
            self.client.get("/api/video/9999/480p/index.m3u8").status_code, 404
        )

    def test_missing_manifest(self):
        """Verify missing manifest."""
        (video_root(self.video.pk) / "480p/index.m3u8").unlink()
        self.assertEqual(
            self.client.get(self.playlist_path()).status_code, 404
        )

    def test_missing_segment(self):
        """Verify missing segment."""
        self.assertEqual(
            self.client.get(self.segment_path("999.ts")).status_code, 404
        )

    def test_anonymous_playlist_and_segment(self):
        """Verify anonymous playlist and segment."""
        self.client.cookies.clear()
        for path in (self.playlist_path(), self.segment_path()):
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_traversal_and_arbitrary_files(self):
        """Verify traversal and arbitrary files."""
        for name in UNSAFE_SEGMENTS:
            with self.subTest(name=name):
                self.assertEqual(
                    self.client.get(self.segment_path(name)).status_code, 404
                )

    def test_processing_video_not_accessible(self):
        """Verify processing video not accessible."""
        Video.objects.filter(pk=self.video.pk).update(status="processing")
        self.assertEqual(
            self.client.get(self.playlist_path()).status_code, 404
        )

    def test_private_files_have_no_public_media_route(self):
        """Verify private files have no public media route."""
        paths = [
            f"/media/videos/{self.video.pk}/480p/index.m3u8",
            f"/media/videos/{self.video.pk}/480p/000.ts",
            "/media/uploads/source.mp4",
        ]
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_cache_failure_falls_back_to_file(self):
        """Verify cache failure falls back to file."""
        with patch("videos.utils.cache.get", side_effect=RedisConnectionError):
            response = self.client.get(self.playlist_path())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"#EXTM3U", response.content)

    def test_symlink_escape_rejected(self):
        """Verify symlink escape rejected."""
        from videos.paths import protected_file

        with patch.object(
            Path,
            "resolve",
            side_effect=[Path("/safe/root"), Path("/outside/000.ts")],
        ):
            from django.http import Http404

            with self.assertRaises(Http404):
                protected_file(self.video, "480p", "000.ts")
