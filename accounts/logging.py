import logging
import re

SENSITIVE_PATH = re.compile(
    r"(/api/(?:activate|password_confirm)/)[^/\s]+/[^/\s]+/?"
)


class RedactTokenPaths(logging.Filter):
    """Remove account activation and reset secrets from log messages."""

    def filter(self, record):
        """Redact account action tokens before emitting the log record."""
        record.msg = SENSITIVE_PATH.sub(r"\1[redacted]/", record.getMessage())
        record.args = ()
        return True
