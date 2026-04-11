from rest_framework import serializers
from .models import Donation


class DonationCreateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=1)


class DonationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Donation
        fields = [
            "id", "first_name", "last_name", "email",
            "amount", "status", "stripe_reference",
            "created_at", "updated_at",
        ]
        read_only_fields = fields
