from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("videos.urls")),
    # Public thumbnails only. Originals and HLS remain in PRIVATE_MEDIA_ROOT.
    re_path(
        r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}
    ),
]
