from rest_framework import serializers
from taggit.serializers import TagListSerializerField, TaggitSerializer
from config.fields import RichTextField
from .models import Video, VideoCategory


class VideoCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoCategory
        fields = ["id", "name", "slug"]
        read_only_fields = ["id", "slug"]


class VideoAuthorSerializer(serializers.Serializer):
    """Minimal author info for public display."""
    id = serializers.IntegerField()
    full_name = serializers.SerializerMethodField()
    profile_picture = serializers.ImageField()
    professional_title = serializers.CharField(allow_null=True)

    def get_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email


class AdminVideoSerializer(TaggitSerializer, serializers.ModelSerializer):
    """Full serializer for admin — all fields including status controls."""
    content = RichTextField()
    tags = TagListSerializerField()
    author_detail = VideoAuthorSerializer(source="author", read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=VideoCategory.objects.all(), write_only=True
    )
    category = VideoCategorySerializer(read_only=True)

    class Meta:
        model = Video
        fields = [
            "id", "author", "author_detail", "category_id", "category", "title", "slug",
            "video_url", "cover_image", "excerpt", "content", "status",
            "rejection_reason", "tags", "view_count", "published_at",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "slug", "view_count",
            "published_at", "created_at", "updated_at",
        ]


class TeacherVideoSerializer(TaggitSerializer, serializers.ModelSerializer):
    """
    Serializer for teachers creating/editing their own videos.
    - Cannot set status directly (goes to pending on submit).
    - Cannot set rejection_reason.
    - Author is set automatically.
    """
    content = RichTextField()
    tags = TagListSerializerField()
    author_detail = VideoAuthorSerializer(source="author", read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=VideoCategory.objects.all(), write_only=True
    )
    category = VideoCategorySerializer(read_only=True)

    class Meta:
        model = Video
        fields = [
            "id", "author", "author_detail", "category_id", "category", "title", "slug",
            "video_url", "cover_image", "excerpt", "content", "status", "tags",
            "published_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "author", "slug", "status",
            "published_at", "created_at", "updated_at",
        ]


class PublicVideoSerializer(TaggitSerializer, serializers.ModelSerializer):
    """Public serializer — no internal fields."""
    content = RichTextField()
    tags = TagListSerializerField()
    category = VideoCategorySerializer(read_only=True)
    author_detail = VideoAuthorSerializer(source="author", read_only=True)

    class Meta:
        model = Video
        fields = [
            "id", "author_detail", "category", "title", "slug",
            "video_url", "cover_image", "excerpt", "content", "tags",
            "view_count", "published_at", "created_at",
        ]
        read_only_fields = fields


class VideoListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for related video cards — no heavy content field."""
    category = VideoCategorySerializer(read_only=True)
    author_detail = VideoAuthorSerializer(source="author", read_only=True)

    class Meta:
        model = Video
        fields = [
            "id", "author_detail", "category", "title", "slug",
            "cover_image", "excerpt", "view_count", "published_at",
        ]
        read_only_fields = fields


class ApproveRejectSerializer(serializers.Serializer):
    """Used only for the reject action to capture reason."""
    reason = serializers.CharField(required=False, allow_blank=True)
