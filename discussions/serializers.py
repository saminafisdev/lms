from rest_framework import serializers
from .models import Post, Reply


def _get_profile_picture(user, request):
    pic = None
    if hasattr(user, "teacherprofile"):
        pic = user.teacherprofile.profile_picture
    elif hasattr(user, "studentprofile"):
        pic = user.studentprofile.profile_picture
    if pic and request:
        return request.build_absolute_uri(pic.url)
    return None


class ReplySerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_role = serializers.SerializerMethodField()
    author_avatar = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Reply
        fields = [
            "id", "post", "author", "author_name", "author_role", "author_avatar",
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

    def get_author_avatar(self, obj):
        return _get_profile_picture(obj.author, self.context.get("request"))

    def get_children(self, obj):
        # Only one level deep — return direct children
        qs = obj.children.select_related("author").all()
        return ReplySerializer(qs, many=True, context=self.context).data


class PostSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_role = serializers.SerializerMethodField()
    author_avatar = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id", "course", "author", "author_name", "author_role", "author_avatar",
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

    def get_author_avatar(self, obj):
        return _get_profile_picture(obj.author, self.context.get("request"))

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
