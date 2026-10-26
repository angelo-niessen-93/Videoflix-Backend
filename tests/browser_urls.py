"""Public thumbnail routing only for the isolated live browser test server."""

from django.conf import settings
from django.urls import re_path
from django.views.static import serve

from config.urls import urlpatterns as application_urls

urlpatterns = [
    *application_urls,
    re_path(
        r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}
    ),
]
