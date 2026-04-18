from rest_framework import serializers

from .models import CourseAnnouncement, SiteAnnouncement


class CourseAnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CourseAnnouncement
        fields = ["id", "title", "body", "created_by", "created_by_name", "created_at"]
        read_only_fields = ["id", "created_by", "created_by_name", "created_at"]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None


class SiteAnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteAnnouncement
        fields = [
            "id", "title_prefix", "main_title", "message",
            "badges", "image", "cta_text", "cta_link",
            "highlights", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
