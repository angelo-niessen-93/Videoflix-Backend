"""Real, unchanged Academy frontend served using installed Live Server."""

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import fakeredis
from django.conf import settings
from django.core import mail
from rq import Queue

FRONTEND_ROOT = Path(
    os.getenv(
        "VIDEOFLIX_FRONTEND_DIR",
        str(Path(settings.BASE_DIR).parent / "Videoflix-Frontend"),
    )
)
FRONTEND_ORIGIN = "http://127.0.0.1:5500"
API_ORIGIN = "http://127.0.0.1:8000"
RESULTS_ROOT = Path(settings.BASE_DIR) / "test-results/browser"
LIVE_SERVER_MODULE = Path.home() / (
    ".vscode/extensions/ritwickdey.liveserver-5.7.10/node_modules/live-server"
)
FAKE_REDIS = fakeredis.FakeRedis()


def browser_queue(name, **kwargs):
    return Queue(name, connection=FAKE_REDIS)


def drain_email_queue():
    queue = browser_queue("default")
    for job in queue.get_jobs():
        job.perform()
        queue.remove(job)
    return mail.outbox[-1]


def mail_link(message):
    return next(
        word
        for word in message.body.split()
        if word.startswith(FRONTEND_ORIGIN)
    )


def start_live_server():
    if not FRONTEND_ROOT.is_dir() or not LIVE_SERVER_MODULE.is_dir():
        raise RuntimeError("Official frontend and Live Server required")
    return subprocess.Popen(
        ["node", "-e", live_server_javascript()],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def wait_for_frontend(process):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Live Server terminated during startup")
        try:
            with urlopen(
                FRONTEND_ORIGIN + "/index.html", timeout=1
            ) as response:
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.1)
    raise RuntimeError("Live Server did not become ready")


def stop_live_server(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def save_browser_evidence(test_name, requests, errors):
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    path = RESULTS_ROOT / f"{test_name}.json"
    path.write_text(
        json.dumps(
            {"requests": requests, "frontend_errors": errors}, indent=2
        ),
        encoding="utf-8",
    )


def database_call(function, *args, **kwargs):
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(function, *args, **kwargs).result(timeout=60)


def live_server_javascript():
    options = {
        "host": "127.0.0.1",
        "port": 5500,
        "root": str(FRONTEND_ROOT),
        "open": False,
        "logLevel": 0,
    }
    return (
        f"require({json.dumps(str(LIVE_SERVER_MODULE))})"
        f".start({json.dumps(options)})"
    )
