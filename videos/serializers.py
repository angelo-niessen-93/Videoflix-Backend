from rest_framework import serializers

from .models import Video


class VideoSerializer(serializers.ModelSerializer):
    """Expose dashboard metadata and a public thumbnail URL."""

    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = [
            "id",
            "created_at",
            "title",
            "description",
            "thumbnail_url",
            "category",
        ]

    def get_thumbnail_url(self, instance) -> str:
        """Build an absolute public thumbnail URL for the client."""
        return self.context["request"].build_absolute_uri(
            instance.thumbnail.url
        )
