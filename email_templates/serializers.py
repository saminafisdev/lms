from rest_framework import serializers
from .models import EmailTemplateConfig


class SendGridTemplateVersionSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    subject = serializers.CharField()
    thumbnail_url = serializers.CharField()
    active = serializers.BooleanField()
    updated_at = serializers.CharField()


class SendGridTemplateSerializer(serializers.Serializer):
    """Represents a template fetched from SendGrid — not a DB model."""

    id = serializers.CharField()
    name = serializers.CharField()
    updated_at = serializers.CharField()
    versions = SendGridTemplateVersionSerializer(many=True)


class EmailTemplateConfigSerializer(serializers.ModelSerializer):
    purpose_display = serializers.CharField(
        source="get_purpose_display", read_only=True
    )
    updated_by_email = serializers.ReadOnlyField(source="updated_by.email")

    class Meta:
        model = EmailTemplateConfig
        fields = [
            "id",
            "purpose",
            "purpose_display",
            "sendgrid_template_id",
            "description",
            "is_active",
            "updated_at",
            "updated_by_email",
        ]
        read_only_fields = ["id", "updated_at", "updated_by_email", "purpose_display"]

    def validate_sendgrid_template_id(self, value):
        if not value.startswith("d-"):
            raise serializers.ValidationError(
                "Invalid SendGrid template ID. It must start with 'd-'."
            )
        return value

    def save(self, **kwargs):
        kwargs["updated_by"] = self.context["request"].user
        return super().save(**kwargs)
