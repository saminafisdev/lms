from rest_framework import serializers
from .models import Door

class AdminDoorSerializer(serializers.ModelSerializer):
    """
    Serializer for admin users, including internal management fields.
    """
    class Meta:
        model = Door
        fields = ["id", "title", "content", "icon", "is_visible", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

class DoorSerializer(serializers.ModelSerializer):
    """
    Public serializer for all users, excludes hidden management fields.
    """
    class Meta:
        model = Door
        fields = ["id", "title", "content", "icon", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
