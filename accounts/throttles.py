import logging

from redis.exceptions import RedisError
from rest_framework.throttling import AnonRateThrottle

logger = logging.getLogger(__name__)


class ResilientAnonThrottle(AnonRateThrottle):
    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except RedisError:
            logger.error("Rate limit infrastructure unavailable")
            return True
