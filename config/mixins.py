# config/mixins.py
from config.utils import generate_unique_slug
from rest_framework import serializers


class SlugMixin:
    """
    Add to any ModelSerializer that has a slug field.
    Handles auto-generation and uniqueness validation.

    Usage:
        class AdminBookSerializer(SlugMixin, serializers.ModelSerializer):
            slug_source_field = 'title'  # field to generate slug from
            ...
    """

    slug_source_field = "title"  # default, override in serializer if needed

    def validate_slug(self, value):
        if value:
            instance = getattr(self, "instance", None)
            model = self.Meta.model
            qs = model.objects.filter(slug=value)
            if instance:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError("This slug is already in use.")
        return value

    def create(self, validated_data):
        if not validated_data.get("slug"):
            source = self.slug_source_field
            validated_data["slug"] = generate_unique_slug(
                self.Meta.model, validated_data[source]
            )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if not validated_data.get("slug"):
            source = self.slug_source_field
            new_value = validated_data.get(source)
            current_value = getattr(instance, source)
            if new_value and new_value != current_value:
                validated_data["slug"] = generate_unique_slug(
                    self.Meta.model, new_value, instance_pk=instance.pk
                )
        return super().update(instance, validated_data)
