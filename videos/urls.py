from django.urls import path

from .views import PlaylistView, SegmentView, VideoListView

urlpatterns = [
    path("video/", VideoListView.as_view(), name="video-list"),
    path(
        "video/<int:movie_id>/<str:resolution>/index.m3u8",
        PlaylistView.as_view(),
        name="playlist",
    ),
    path(
        "video/<int:movie_id>/<str:resolution>/<str:segment>/",
        SegmentView.as_view(),
        name="segment",
    ),
]
