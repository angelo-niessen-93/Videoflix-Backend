import logging
import re

SENSITIVE_PATH = re.compile(
    r"(/api/(?:activate|password_confirm)/)[^/\s]+/[^/\s]+/?"
)


class RedactTokenPaths(logging.Filter):
    def filter(self, record):
        record.msg = SENSITIVE_PATH.sub(r"\1[redacted]/", record.getMessage())
        record.args = ()
        return True
