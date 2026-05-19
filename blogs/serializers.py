# blogs/serializers.py
from config.mixins import SlugMixin
from rest_framework import serializers
from taggit.serializers import TagListSerializerField, TaggitSerializer
from config.fields import RichTextField
from .models import Blog, BlogCategory


class BlogCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogCategory
        fields = ["id", "name", "slug"]
        read_only_fields = ["id", "slug"]


class BlogAuthorSerializer(serializers.Serializer):
    """Minimal author info for public display."""

    id = serializers.IntegerField()
    full_name = serializers.SerializerMethodField()
    profile_picture = serializers.ImageField()
    professional_title = serializers.CharField(allow_null=True)
    role = serializers.CharField(source="user.role")

    def get_full_name(self, obj):
        if getattr(obj.user, "role", None) == "admin":
            return "Sakeena Institute"
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email


class AdminBlogSerializer(SlugMixin, TaggitSerializer, serializers.ModelSerializer):
    """Full serializer for admin — all fields including status controls."""

    slug_source_field = "title"
    content = RichTextField()
    tags = TagListSerializerField()
    reading_time = serializers.ReadOnlyField()
    author_detail = BlogAuthorSerializer(source="author", read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=BlogCategory.objects.all(), write_only=True, required=False, allow_null=True
    )
    category = BlogCategorySerializer(read_only=True)

    class Meta:
        model = Blog
        fields = [
            "id",
            "author",
            "author_detail",
            "category_id",
            "category",
            "title",
            "slug",
            "cover_image",
            "excerpt",
            "content",
            "status",
            "rejection_reason",
            "tags",
            "view_count",
            "reading_time",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "view_count",
            "reading_time",
            "published_at",
            "created_at",
            "updated_at",
        ]


class TeacherBlogSerializer(TaggitSerializer, serializers.ModelSerializer):
    """
    Serializer for teachers creating/editing their own blogs.
    - Cannot set status directly (goes to pending on submit).
    - Cannot set rejection_reason.
    - Author is set automatically.
    """

    content = RichTextField()
    tags = TagListSerializerField()
    reading_time = serializers.ReadOnlyField()
    author_detail = BlogAuthorSerializer(source="author", read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=BlogCategory.objects.all(), write_only=True, required=False, allow_null=True
    )
    category = BlogCategorySerializer(read_only=True)

    class Meta:
        model = Blog
        fields = [
            "id",
            "author",
            "author_detail",
            "category_id",
            "category",
            "title",
            "slug",
            "cover_image",
            "excerpt",
            "content",
            "status",
            "tags",
            "reading_time",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "author",
            "slug",
            "status",
            "reading_time",
            "published_at",
            "created_at",
            "updated_at",
        ]


class PublicBlogSerializer(TaggitSerializer, serializers.ModelSerializer):
    """Public serializer — no internal fields."""

    content = RichTextField()
    tags = TagListSerializerField()
    reading_time = serializers.ReadOnlyField()
    category = BlogCategorySerializer(read_only=True)
    author_detail = BlogAuthorSerializer(source="author", read_only=True)

    class Meta:
        model = Blog
        fields = [
            "id",
            "author_detail",
            "category",
            "title",
            "slug",
            "cover_image",
            "excerpt",
            "content",
            "tags",
            "view_count",
            "reading_time",
            "published_at",
            "created_at",
        ]
        read_only_fields = fields


class ApproveRejectSerializer(serializers.Serializer):
    """Used only for the reject action to capture reason."""

    reason = serializers.CharField(required=False, allow_blank=True)
