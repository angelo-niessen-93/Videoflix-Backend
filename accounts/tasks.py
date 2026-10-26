import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from redis.exceptions import RedisError

from config.jobs import queue_task

from .email_assets import attach_logo
from .models import EmailJob
from .tokens import encoded_uid, valid_token

logger = logging.getLogger(__name__)


def enqueue_email(job_id: int):
    try:
        job = queue_task("default", send_account_email, job_id, 120, 3)
        EmailJob.objects.filter(pk=job_id).update(job_id=job.id)
    except RedisError as error:
        EmailJob.objects.filter(pk=job_id).update(
            status="failed", error=type(error).__name__
        )
        logger.error("Email queue unavailable; job %s retained", job_id)


def frontend_link(job) -> str:
    path = (
        settings.ACTIVATION_PATH
        if job.purpose == "activation"
        else settings.PASSWORD_RESET_PATH
    )
    return (
        f"{settings.FRONTEND_URL}{path}"
        f"?uid={encoded_uid(job.user)}&token={job.token}"
    )


def email_context(job) -> dict:
    activation = job.purpose == "activation"
    timeout = (
        settings.ACTIVATION_TIMEOUT
        if activation
        else settings.PASSWORD_RESET_TIMEOUT
    )
    return {
        "link": frontend_link(job),
        "activation": activation,
        "valid_minutes": max(1, timeout // 60),
    }


def deliver_email(job):
    context = email_context(job)
    message = build_email(job, context)
    message.attach_alternative(
        render_to_string("emails/account.html", context), "text/html"
    )
    attach_logo(message)
    message.send(fail_silently=False)


def send_account_email(job_id: int):
    try:
        process_email(job_id)
    except Exception as error:
        EmailJob.objects.filter(pk=job_id).update(
            status="failed", error=type(error).__name__
        )
        logger.error("Email job %s failed (%s)", job_id, type(error).__name__)
        raise


@transaction.atomic
def process_email(job_id: int):
    jobs = EmailJob.objects.select_for_update().select_related("user")
    job = jobs.get(pk=job_id)
    if job.status == "sent":
        return
    if not valid_token(job.user, job.token, job.purpose):
        job.status = "expired"
    else:
        deliver_email(job)
        job.status = "sent"
    job.error = ""
    job.save(update_fields=["status", "error"])


def build_email(job, context):
    subject = (
        "Confirm your email"
        if context["activation"]
        else "Reset your Password"
    )
    return EmailMultiAlternatives(
        subject,
        render_to_string("emails/account.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [job.user.email],
    )
