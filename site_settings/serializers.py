from rest_framework import serializers
from config.fields import RichTextField
from .models import SiteSettings, Testimonial


class SiteSettingsSerializer(serializers.ModelSerializer):
    long_about = RichTextField(required=False, allow_blank=True)
    privacy_policy = RichTextField(required=False, allow_blank=True)
    terms_and_conditions = RichTextField(required=False, allow_blank=True)

    class Meta:
        model = SiteSettings
        fields = [
            "short_about",
            "long_about",
            "privacy_policy",
            "terms_and_conditions",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class TestimonialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Testimonial
        fields = ["id", "name", "picture", "body", "is_active", "order", "created_at"]
        read_only_fields = ["created_at"]
