"""Run the same isolated suite on a dedicated PostgreSQL test database."""

from .settings import DATABASES as POSTGRES_DATABASES
from .test_settings import *  # noqa: F403

DATABASES = POSTGRES_DATABASES
DATABASES["default"]["CONN_MAX_AGE"] = 0
