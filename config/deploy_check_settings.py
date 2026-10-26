"""Production security validation without connecting to external services."""

import os

os.environ["DJANGO_DEBUG"] = "false"
os.environ["COOKIE_SECURE"] = "true"
os.environ.setdefault("DJANGO_SECRET_KEY", "deploy-check-only-" * 5)

from .settings import *  # noqa: E402,F403
