"""Explicitly isolated tests; never use production DB, Redis or SMTP."""

import os
import tempfile

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key-" * 5)

from .settings import *  # noqa: E402,F403

DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
}
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MEDIA_ROOT = tempfile.mkdtemp(prefix="videoflix-test-public-")
PRIVATE_MEDIA_ROOT = tempfile.mkdtemp(prefix="videoflix-test-private-")
SECURE_SSL_REDIRECT = False
COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
ALLOWED_HOSTS = ["testserver", "localhost"]
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa: F405

TEST_RUNNER = "config.test_runner.IsolatedRunner"
