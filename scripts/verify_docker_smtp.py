"""Actual RQ-to-SMTP transport inside the disposable Docker network only."""

from socketserver import ThreadingTCPServer
from threading import Thread

from django.conf import settings
from django.db import connection

from accounts.models import EmailJob, User
from accounts.services import schedule_email
from scripts.verify_infrastructure import require, wait_for_status
from tests.smtp_support import SmtpHandler


def verify_isolation():
    require(
        connection.settings_dict["NAME"].endswith("_acceptance"),
        "Disposable acceptance database required",
    )
    verify_smtp_config()


def verify_smtp_config():
    expected = {
        "EMAIL_HOST": "web",
        "EMAIL_PORT": 1025,
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_USE_TLS": False,
        "EMAIL_USE_SSL": False,
        "EMAIL_HOST_USER": "",
        "EMAIL_HOST_PASSWORD": "",
    }
    for key, value in expected.items():
        require(getattr(settings, key) == value, f"Unsafe SMTP setting: {key}")


def send_and_verify(server):
    user = User.objects.filter(is_active=True, is_superuser=False).first()
    require(user is not None, "Run HTTP registration acceptance first")
    schedule_email(user, "reset")
    job = EmailJob.objects.filter(user=user).latest("pk")
    wait_for_status(job, "sent")
    require(bool(job.job_id), "No asynchronous RQ job ID")
    require(len(server.messages) == 1, "SMTP sink did not receive one message")
    require(user.email.encode() in server.messages[0], "Wrong SMTP recipient")


def main():
    verify_isolation()
    with ThreadingTCPServer(("0.0.0.0", 1025), SmtpHandler) as server:
        server.daemon_threads = True
        server.messages = []
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            send_and_verify(server)
        finally:
            server.shutdown()
            thread.join(timeout=5)
    print("PASS: .env SMTP settings -> real RQ worker -> internal SMTP sink")
