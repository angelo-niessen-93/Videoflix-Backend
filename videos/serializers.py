from rest_framework import serializers

from .models import Video


class VideoSerializer(serializers.ModelSerializer):
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
        return self.context["request"].build_absolute_uri(
            instance.thumbnail.url
        )
