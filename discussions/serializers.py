from rest_framework import serializers
from .models import Post, Reply


class ReplySerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_role = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Reply
        fields = [
            "id", "post", "author", "author_name", "author_role",
            "body", "parent", "children", "created_at", "updated_at",
        ]
        extra_kwargs = {
            "post": {"read_only": True},
            "author": {"read_only": True},
        }

    def get_author_name(self, obj):
        u = obj.author
        full = f"{u.first_name} {u.last_name}".strip()
        return full or u.email

    def get_author_role(self, obj):
        return obj.author.role

    def get_children(self, obj):
        # Only one level deep — return direct children
        qs = obj.children.select_related("author").all()
        return ReplySerializer(qs, many=True, context=self.context).data


class PostSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_role = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id", "course", "author", "author_name", "author_role",
            "title", "body", "is_pinned", "is_closed",
            "reply_count", "created_at", "updated_at",
        ]
        extra_kwargs = {
            "course": {"read_only": True},
            "author": {"read_only": True},
            "is_pinned": {"read_only": True},
            "is_closed": {"read_only": True},
        }

    def get_author_name(self, obj):
        u = obj.author
        full = f"{u.first_name} {u.last_name}".strip()
        return full or u.email

    def get_author_role(self, obj):
        return obj.author.role

    def get_reply_count(self, obj):
        return obj.replies.count()


class PostDetailSerializer(PostSerializer):
    """Post with full replies (used in retrieve)."""
    replies = serializers.SerializerMethodField()

    class Meta(PostSerializer.Meta):
        fields = PostSerializer.Meta.fields + ["replies"]

    def get_replies(self, obj):
        # Top-level replies only; children are nested inside each reply
        qs = obj.replies.filter(parent__isnull=True).select_related("author").prefetch_related("children__author")
        return ReplySerializer(qs, many=True, context=self.context).data
