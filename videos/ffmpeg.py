import json
import subprocess
from pathlib import Path

from django.conf import settings

from .paths import RESOLUTIONS, safe_segment

PROBE_FLAGS = [
    "-v",
    "error",
    "-select_streams",
    "v:0",
    "-show_entries",
    "stream=width,height,codec_name:format=duration",
    "-of",
    "json",
]
ENCODING_FLAGS = [
    "-map",
    "0:v:0",
    "-map",
    "0:a:0?",
    "-c:v",
    "libx264",
    "-preset",
    "fast",
    "-crf",
    "23",
    "-pix_fmt",
    "yuv420p",
    "-flags",
    "+cgop",
    "-force_key_frames",
    "expr:gte(t,n_forced*6)",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
]
HLS_FLAGS = [
    "-f",
    "hls",
    "-hls_time",
    "6",
    "-hls_list_size",
    "0",
    "-hls_playlist_type",
    "vod",
    "-hls_flags",
    "independent_segments",
]
THUMBNAIL_FLAGS = ["-frames:v", "1", "-vf", "scale=640:-2"]


def ffmpeg_input(source: Path) -> list[str]:
    return [
        settings.FFMPEG_BINARY,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-threads",
        str(settings.FFMPEG_THREADS),
    ]


def run_process(arguments: list[str], timeout: int):
    return subprocess.run(
        arguments,
        check=True,
        capture_output=True,
        timeout=timeout,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def probe_video(source: Path) -> dict:
    arguments = [settings.FFPROBE_BINARY, *PROBE_FLAGS, str(source)]
    output = run_process(arguments, 30)
    metadata = json.loads(output.stdout)
    stream = metadata["streams"][0]
    if min(int(stream["height"]), int(stream["width"])) < 2:
        raise ValueError("Invalid video dimensions")
    return stream


def target_resolutions(height: int) -> list[str]:
    return [name for name in RESOLUTIONS if int(name[:-1]) <= height]


def encoding_arguments(height: int) -> list[str]:
    return [
        *ENCODING_FLAGS,
        "-vf",
        f"scale=trunc(oh*dar/2)*2:{height},setsar=1",
        "-threads",
        str(settings.FFMPEG_THREADS),
    ]


def convert_variant(source: Path, folder: Path, height: int):
    folder.mkdir(parents=True, exist_ok=True)
    arguments = ffmpeg_input(source) + encoding_arguments(height)
    arguments += HLS_FLAGS + [
        "-hls_segment_filename",
        str(folder / "%03d.ts"),
        str(folder / "index.m3u8"),
    ]
    run_process(arguments, settings.FFMPEG_TIMEOUT)


def create_thumbnail(source: Path, destination: Path):
    arguments = ffmpeg_input(source) + THUMBNAIL_FLAGS
    run_process([*arguments, str(destination)], 60)


def playlist_segments(folder: Path) -> list[str]:
    text = (folder / "index.m3u8").read_text(encoding="utf-8")
    if not text.startswith("#EXTM3U") or "#EXT-X-ENDLIST" not in text:
        raise ValueError("Incomplete playlist")
    segments = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not segments or any(not safe_segment(name) for name in segments):
        raise ValueError("Unsafe or empty playlist")
    if any(not (folder / name).is_file() for name in segments):
        raise ValueError("Missing HLS segment")
    return segments


def validate_variant(folder: Path, height: int):
    for name in playlist_segments(folder):
        segment = folder / name
        metadata = probe_video(segment)
        if metadata["codec_name"] != "h264" or metadata["height"] != height:
            raise ValueError("Unexpected HLS encoding")


def complete_variant(folder: Path, height: int) -> bool:
    try:
        validate_variant(folder, height)
        return True
    except (
        OSError,
        ValueError,
        KeyError,
        IndexError,
        subprocess.SubprocessError,
    ):
        return False
