from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.static import serve
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView

from .models import Video
from .paths import protected_file, safe_segment
from .serializers import VideoSerializer
from .thumbnails import repair_thumbnail
from .utils import playlist_response_text


def thumbnail_file(request, path):
    """Repair a deleted public image on access without touching HLS files."""
    try:
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    except Http404:
        video = get_object_or_404(
            Video, thumbnail=path, status=Video.Status.READY
        )
        video = repair_thumbnail(video.pk)
        return redirect(video.thumbnail.url)


class VideoListView(ListAPIView):
    """List playable videos with published resolutions and thumbnails."""

    serializer_class = VideoSerializer
    pagination_class = None
    queryset = (
        Video.objects.filter(status=Video.Status.READY)
        .exclude(thumbnail="")
        .exclude(resolutions=[])
    )


class PlaylistView(APIView):
    """Serve a private HLS playlist to an authenticated viewer."""

    def get(self, request, movie_id, resolution):
        """Return an authorized playlist with private cache headers."""
        video = get_object_or_404(
            Video, pk=movie_id, status=Video.Status.READY
        )
        path = protected_file(video, resolution, "index.m3u8")
        response = HttpResponse(
            playlist_response_text(path),
            content_type="application/vnd.apple.mpegurl",
        )
        response["Cache-Control"] = "private, no-store"
        return response


class SegmentView(APIView):
    """Serve a validated private MPEG-TS segment to a viewer."""

    def get(self, request, movie_id, resolution, segment):
        """Stream an authorized numbered segment with private cache headers."""
        video = get_object_or_404(
            Video, pk=movie_id, status=Video.Status.READY
        )
        if not safe_segment(segment):
            raise Http404
        path = protected_file(video, resolution, segment)
        response = FileResponse(path.open("rb"), content_type="video/MP2T")
        response["Cache-Control"] = "private, no-store"
        return response
