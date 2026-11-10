import logging

from redis.exceptions import RedisError
from rest_framework.throttling import AnonRateThrottle

logger = logging.getLogger(__name__)


class ResilientAnonThrottle(AnonRateThrottle):
    """Continue serving requests when the Redis throttle is unavailable."""

    def allow_request(self, request, view):
        """Apply throttling while tolerating a logged Redis outage."""
        try:
            return super().allow_request(request, view)
        except RedisError:
            logger.error("Rate limit infrastructure unavailable")
            return True
