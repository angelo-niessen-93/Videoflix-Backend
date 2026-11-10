from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from videos.views import thumbnail_file

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("videos.urls")),
    re_path(r"^media/(?P<path>thumbnails/.*)$", thumbnail_file),
    # Public thumbnails only. Originals and HLS remain in PRIVATE_MEDIA_ROOT.
    re_path(
        r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}
    ),
]
