"""Actual SMTP delivery to a private loopback sink, never a mail provider."""

from email import policy
from email.parser import BytesParser

from django.test import override_settings

from accounts.models import EmailJob
from accounts.services import schedule_email
from accounts.tasks import send_account_email

from .helpers import ApiCase
from .smtp_support import local_smtp_server


class SmtpDeliveryTests(ApiCase):
    """Exercise smtp delivery behavior with isolated fixtures."""

    def deliver_to_sink(self, purpose):
        """Send an account email to the loopback SMTP capture server."""
        with local_smtp_server() as server:
            with override_settings(**smtp_settings(server.server_address[1])):
                schedule_email(self.user, purpose)
                send_account_email(EmailJob.objects.get().pk)
            self.assertEqual(len(server.messages), 1)
            message = BytesParser(policy=policy.default).parsebytes(
                server.messages[0]
            )
        self.assertEqual(EmailJob.objects.get().status, "sent")
        self.assertEqual(message["To"], self.user.email)
        return message

    def assert_message_parts(self, message, page):
        """Check message parts in the integration result."""
        text = message.get_body(preferencelist=("plain",)).get_content()
        html = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn(page + "?uid=", text)
        self.assertTrue("token=" in text and "token=" in html)
        self.assertTrue("cid:videoflix-logo" in html)
        self.assert_inline_logo(message)

    def assert_inline_logo(self, message):
        """Check inline logo in the integration result."""
        images = [
            part
            for part in message.walk()
            if part.get_content_maintype() == "image"
        ]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["Content-ID"], "<videoflix-logo>")
        self.assertTrue(
            images[0].get_payload(decode=True).startswith(b"\x89PNG")
        )

    def test_activation_delivered_over_local_smtp(self):
        """Verify activation delivered over local smtp."""
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        message = self.deliver_to_sink("activation")
        self.assertEqual(message["Subject"], "Confirm your email")
        self.assert_message_parts(message, "/pages/auth/activate.html")

    def test_reset_delivered_over_local_smtp(self):
        """Verify reset delivered over local smtp."""
        message = self.deliver_to_sink("reset")
        self.assertEqual(message["Subject"], "Reset your Password")
        self.assert_message_parts(message, "/pages/auth/confirm_password.html")


def smtp_settings(port):
    """Configure isolated plaintext delivery to the local SMTP sink."""
    return {
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_HOST": "127.0.0.1",
        "EMAIL_PORT": port,
        "EMAIL_HOST_USER": "",
        "EMAIL_HOST_PASSWORD": "",
        "EMAIL_USE_TLS": False,
        "EMAIL_USE_SSL": False,
        "EMAIL_TIMEOUT": 5,
    }
