import os
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch
from urllib.parse import urlsplit

from django.conf import settings
from django.test import LiveServerTestCase, override_settings, tag

from accounts.logging import SENSITIVE_PATH

from .browser_support import (
    API_ORIGIN,
    FAKE_REDIS,
    FRONTEND_ORIGIN,
    RESULTS_ROOT,
    browser_queue,
    database_call,
    drain_email_queue,
    mail_link,
    save_browser_evidence,
    start_live_server,
    stop_live_server,
    wait_for_frontend,
)
from .helpers import NEW_PASSWORD, PASSWORD, create_user
from .test_ffmpeg import generate_source, source_video

PLAYBACK_READY = (
    "height => { const v = document.getElementById('overlayVideo');"
    "return v.currentTime > 0 && v.videoHeight === height; }"
)
RUN_BROWSER = os.getenv("VIDEOFLIX_BROWSER_TESTS") == "1"


@tag("browser")
@skipUnless(
    RUN_BROWSER, "Set VIDEOFLIX_BROWSER_TESTS=1 for real browser tests"
)
@override_settings(ROOT_URLCONF="tests.browser_urls")
class BrowserIntegrationTests(LiveServerTestCase):
    host = "127.0.0.1"
    port = 8000

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.live_frontend = start_live_server()
        cls.addClassCleanup(stop_live_server, cls.live_frontend)
        wait_for_frontend(cls.live_frontend)

    def setUp(self):
        super().setUp()
        self.setup_queue()
        self.setup_browser()
        self.requests, self.frontend_errors = [], []
        self.page.on("response", self.record_response)
        self.page.on(
            "pageerror",
            lambda error: self.frontend_errors.append(error.message),
        )

    def tearDown(self):
        save_browser_evidence(
            self._testMethodName, self.requests, self.frontend_errors
        )
        super().tearDown()

    def record_response(self, response):
        if response.url.startswith(API_ORIGIN):
            request = response.request
            self.requests.append(
                {
                    "path": SENSITIVE_PATH.sub(
                        r"\1[redacted]/", urlsplit(response.url).path
                    ),
                    "method": request.method,
                    "status": response.status,
                    "origin": request.all_headers().get("origin"),
                    "csrf_header": "x-csrftoken" in request.headers,
                }
            )

    def submit(self, endpoint, button):
        with self.page.expect_response(
            lambda response: (
                endpoint in response.url and response.request.method == "POST"
            )
        ) as response:
            self.page.get_by_role("button", name=button, exact=True).click()
        return response.value

    def fill_login(self, email, password):
        self.page.goto(FRONTEND_ORIGIN + "/pages/auth/login.html")
        self.page.locator("#email").fill(email)
        self.page.locator("#password").fill(password)
        return self.submit("/api/login/", "Log in")

    def create_playable_video(self):
        from videos.tasks import convert_video

        source = Path(settings.PRIVATE_MEDIA_ROOT) / "browser-source.mp4"
        source.parent.mkdir(parents=True, exist_ok=True)
        generate_source(source)
        video = source_video(source)
        convert_video(video.pk)
        return video

    def register_account(self, email):
        self.page.goto(FRONTEND_ORIGIN + "/pages/auth/register.html")
        self.page.locator("#email").fill(email)
        self.page.locator("#password").fill(PASSWORD)
        self.page.locator("#confirmed_password").fill(PASSWORD)
        self.page.locator("label[for=privacy_policy] .checkbox_icon").click()
        self.assertEqual(
            self.submit("/api/register/", "Get started").status, 201
        )
        self.page.goto(mail_link(database_call(drain_email_queue)))
        self.page.wait_for_url("**/pages/auth/login.html", timeout=10000)

    def assert_jwt_cookies(self):
        cookies = {cookie["name"]: cookie for cookie in self.context.cookies()}
        for name in ("access_token", "refresh_token"):
            self.assertTrue(cookies[name]["httpOnly"])
            self.assertEqual(cookies[name]["sameSite"], "Lax")
            self.assertEqual(cookies[name]["domain"], "127.0.0.1")

    def assert_playback(self):
        self.page.locator("#playButton").click()
        for resolution in ("480p", "720p", "1080p"):
            self.page.locator("#setResolution").select_option(resolution)
            self.page.wait_for_function(
                PLAYBACK_READY, arg=int(resolution[:-1]), timeout=20000
            )
        self.page.screenshot(path=str(RESULTS_ROOT / "hls-playback.png"))
        self.page.keyboard.press("Escape")

    def assert_refresh_interval(self):
        with self.page.expect_response("**/api/token/refresh/") as response:
            self.page.clock.fast_forward(20 * 60 * 1000 + 1)
        self.assertEqual(response.value.status, 200)
        self.page.clock.resume()

    def assert_logout(self):
        with self.page.expect_response("**/api/logout/") as response:
            self.page.get_by_label("logout", exact=True).click()
        self.assertEqual(response.value.status, 200)
        cookies = {cookie["name"] for cookie in self.context.cookies()}
        self.assertNotIn("access_token", cookies)
        self.assertNotIn("refresh_token", cookies)

    def test_registration_activation_login_playback_refresh_logout(self):
        RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        database_call(self.create_playable_video)
        self.register_account("browser-register@example.com")
        response = self.fill_login("browser-register@example.com", PASSWORD)
        self.assertEqual(response.status, 200)
        self.wait_for_dashboard()
        self.assert_jwt_cookies()
        self.assert_playback()
        self.assert_refresh_interval()
        self.assert_logout()

    def test_forgot_password_reset_and_login(self):
        user = database_call(create_user, email="browser-reset@example.com")
        self.page.goto(FRONTEND_ORIGIN + "/pages/auth/forgot_password.html")
        self.page.locator("#forgot_email").fill(user.email)
        response = self.submit("/api/password_reset/", "Send email")
        self.assertEqual(response.status, 200)
        self.page.goto(mail_link(database_call(drain_email_queue)))
        self.submit_new_password()
        self.assertEqual(self.fill_login(user.email, PASSWORD).status, 400)
        self.assertEqual(self.fill_login(user.email, NEW_PASSWORD).status, 200)

    def setup_browser(self):
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(
            channel=os.getenv("PLAYWRIGHT_CHANNEL", "msedge"), headless=True
        )
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context()
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.clock.install()

    def setup_queue(self):
        FAKE_REDIS.flushall()
        queue_patch = patch(
            "config.jobs.django_rq.get_queue", side_effect=browser_queue
        )
        queue_patch.start()
        self.addCleanup(queue_patch.stop)

    def wait_for_dashboard(self):
        self.page.wait_for_url("**/pages/video_list/index.html")
        self.page.wait_for_function(
            "document.getElementById('videoTitle').textContent"
            " === 'Integration clip'"
        )

    def submit_new_password(self):
        self.page.locator("#password").fill(NEW_PASSWORD)
        self.page.locator("#repeated_password").fill(NEW_PASSWORD)
        response = self.submit("/api/password_confirm/", "Reset password")
        self.assertEqual(response.status, 200)
