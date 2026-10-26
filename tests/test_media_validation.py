from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from videos.ffmpeg import complete_variant, playlist_segments


class PlaylistValidationTests(SimpleTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)

    def write_playlist(self, content):
        (self.folder / "index.m3u8").write_text(content, encoding="utf-8")

    def test_incomplete_playlist_rejected(self):
        self.write_playlist("#EXTM3U\n000.ts\n")
        with self.assertRaises(ValueError):
            playlist_segments(self.folder)

    def test_path_in_playlist_rejected(self):
        self.write_playlist("#EXTM3U\n../000.ts\n#EXT-X-ENDLIST\n")
        with self.assertRaises(ValueError):
            playlist_segments(self.folder)

    def test_empty_playlist_rejected(self):
        self.write_playlist("#EXTM3U\n#EXT-X-ENDLIST\n")
        with self.assertRaises(ValueError):
            playlist_segments(self.folder)

    def test_missing_segment_rejected(self):
        self.write_playlist("#EXTM3U\n000.ts\n#EXT-X-ENDLIST\n")
        with self.assertRaises(ValueError):
            playlist_segments(self.folder)

    def test_missing_variant_is_not_complete(self):
        self.assertFalse(complete_variant(self.folder, 480))
