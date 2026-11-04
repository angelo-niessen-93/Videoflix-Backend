"""Render the actual mail templates at mobile and desktop sizes in Edge."""

import base64
import os
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase, tag


@tag("browser")
@skipUnless(
    os.getenv("VIDEOFLIX_BROWSER_TESTS") == "1", "Enable browser tests"
)
class EmailRenderingTests(SimpleTestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(
            channel=os.getenv("PLAYWRIGHT_CHANNEL", "msedge"), headless=True
        )
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)

    def assert_layout(self, activation):
        html, link = rendered_email(activation)
        caption = "Activate account" if activation else "Reset password"
        for width in (320, 390, 1024):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 900})
                self.page.set_content(html)
                self.assert_button(caption, link, width)
                self.assertTrue(
                    self.page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    )
                )
                self.save_preview(activation, width)

    def assert_button(self, caption, link, width):
        button = self.page.get_by_role("link", name=caption, exact=True)
        self.assertEqual(button.get_attribute("href"), link)
        bounds = button.bounding_box()
        self.assertGreaterEqual(bounds["height"], 44)
        self.assertGreaterEqual(bounds["x"], 0)
        self.assertLessEqual(bounds["x"] + bounds["width"], width)
        self.assertTrue(
            self.page.locator("img").evaluate(
                "image => image.complete && image.naturalWidth > 0"
            )
        )

    def save_preview(self, activation, width):
        root = Path(settings.BASE_DIR) / "test-results/email-previews"
        root.mkdir(parents=True, exist_ok=True)
        purpose = "activation" if activation else "reset"
        self.page.screenshot(
            path=str(root / f"{purpose}-{width}.png"), full_page=True
        )

    def test_activation_mobile_and_desktop(self):
        self.assert_layout(True)

    def test_reset_mobile_and_desktop(self):
        self.assert_layout(False)


def rendered_email(activation):
    page = "activate" if activation else "confirm_password"
    link = f"http://127.0.0.1:5500/pages/auth/{page}.html?uid=example&token=example"
    html = render_to_string(
        "emails/account.html",
        {"activation": activation, "link": link, "valid_minutes": 60},
    )
    logo = Path(settings.BASE_DIR) / "templates/emails/assets/logo.png"
    encoded = base64.b64encode(logo.read_bytes()).decode("ascii")
    return html.replace(
        "cid:videoflix-logo", "data:image/png;base64," + encoded
    ), link
