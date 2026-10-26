from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView

from .models import Video
from .paths import protected_file, safe_segment
from .serializers import VideoSerializer
from .utils import playlist_response_text


class VideoListView(ListAPIView):
    serializer_class = VideoSerializer
    pagination_class = None
    queryset = (
        Video.objects.filter(status=Video.Status.READY)
        .exclude(thumbnail="")
        .exclude(resolutions=[])
    )


class PlaylistView(APIView):
    def get(self, request, movie_id, resolution):
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
    def get(self, request, movie_id, resolution, segment):
        video = get_object_or_404(
            Video, pk=movie_id, status=Video.Status.READY
        )
        if not safe_segment(segment):
            raise Http404
        path = protected_file(video, resolution, segment)
        response = FileResponse(path.open("rb"), content_type="video/MP2T")
        response["Cache-Control"] = "private, no-store"
        return response
