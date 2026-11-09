"""Opt-in HTTP acceptance on the disposable Docker acceptance database."""

import json
import os
import re
import secrets
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from django.conf import settings

from accounts.models import EmailJob, User
from accounts.tokens import encoded_uid
from scripts.verify_infrastructure import require, wait_for_status
from videos.models import Video

BASE = "http://127.0.0.1:8000"
SUCCESS = (
    "PASS: real HTTP admin, CSS/JS, registration, activation, cookies, "
    "API, thumbnails, protected HLS, refresh and logout"
)


def encode_body(data):
    return (
        data.encode() if isinstance(data, str) else json.dumps(data).encode()
    )


def request(opener, path, data=None, content_type="application/json"):
    headers = {"Origin": settings.FRONTEND_URL}
    if data is not None:
        headers["Content-Type"] = content_type
        data = encode_body(data)
    try:
        response = opener.open(Request(BASE + path, data, headers), timeout=15)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.read(), response.headers


def json_request(opener, path, data, expected=200):
    status, body, _ = request(opener, path, data)
    require(
        status == expected, f"HTTP {path}: expected {expected}, got {status}"
    )
    return json.loads(body)


def verify_admin(opener, user):
    status, body, _ = request(opener, "/admin/login/")
    require(status == 200, "Admin login page failed")
    verify_static_assets(opener, body)
    csrf = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', body)
    form = admin_form(user, csrf[1].decode())
    status, body, _ = request(
        opener, "/admin/login/", form, "application/x-www-form-urlencoded"
    )
    require(
        status == 200 and b"/admin/logout/" in body, "Admin email login failed"
    )
    verify_static_assets(opener, body)


def admin_form(user, csrf):
    return urlencode(
        {
            "username": user.email,
            "password": os.environ["DJANGO_SUPERUSER_PASSWORD"],
            "csrfmiddlewaretoken": csrf,
            "next": "/admin/",
        }
    )


def verify_static_assets(opener, page):
    assets = re.findall(rb'(?:href|src)="(/static/[^"?]+)', page)
    require(bool(assets), "Admin has no static references")
    for asset in set(assets):
        status, body, headers = request(opener, asset.decode())
        require(status == 200 and body, "Admin static asset failed")
        expected = "css" if asset.endswith(b".css") else "javascript"
        require(
            expected in headers["Content-Type"], "Wrong static content type"
        )


def verify_registration(opener):
    password = secrets.token_urlsafe(32)
    email = secrets.token_hex(12) + "@example.invalid"
    data = dict(email=email, password=password, confirmed_password=password)
    result = json_request(opener, "/api/register/", data, 201)
    user = User.objects.get(pk=result["user"]["id"])
    wait_for_status(EmailJob.objects.get(user=user), "sent")
    path = f"/api/activate/{encoded_uid(user)}/{result['token']}/"
    require(request(opener, path)[0] == 200, "HTTP activation failed")
    json_request(opener, "/api/login/", {"email": email, "password": password})
    require(request(opener, "/api/video/")[0] == 200, "Video API failed")


def verify_playback(opener):
    video = Video.objects.filter(status="ready").first()
    require(video is not None, "Run verify_infrastructure.main first")
    for resolution in video.resolutions:
        verify_variant_http(opener, video.pk, resolution)
    status, body, _ = request(opener, video.thumbnail.url)
    require(status == 200 and body, "Public thumbnail failed with DEBUG=False")
    anonymous = build_opener()
    path = f"/api/video/{video.pk}/480p/index.m3u8"
    require(request(anonymous, path)[0] == 401, "Anonymous HLS was exposed")
    require(
        request(anonymous, "/private_media/" + video.upload.name)[0] == 404,
        "Private original was exposed",
    )


def verify_variant_http(opener, video_id, resolution):
    base = f"/api/video/{video_id}/{resolution}/"
    status, body, _ = request(opener, base + "index.m3u8")
    require(status == 200 and body.startswith(b"#EXTM3U"), "HTTP HLS failed")
    segments = [
        line
        for line in body.decode().splitlines()
        if line and not line.startswith("#")
    ]
    require(bool(segments), "Empty HTTP HLS playlist")
    for segment in segments:
        status, body, _ = request(opener, base + segment)
        require(status == 200 and body[0] == 0x47, "HTTP MPEG-TS failed")


def verify_refresh_logout(opener):
    json_request(opener, "/api/token/refresh/", {})
    json_request(opener, "/api/logout/", {})
    require(request(opener, "/api/video/")[0] == 401, "Logout kept access")


def main():
    from scripts.verify_infrastructure import verify_isolation

    verify_isolation()
    user = User.objects.get(username=os.environ["DJANGO_SUPERUSER_USERNAME"])
    require(user.is_superuser, "Automatic superuser missing")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    verify_admin(opener, user)
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    verify_registration(opener)
    verify_playback(opener)
    verify_refresh_logout(opener)
    print(SUCCESS)
