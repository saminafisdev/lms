from rest_framework import serializers
from .models import MembershipPlan, UserMembership


class MembershipPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipPlan
        fields = ["name", "description", "price", "duration_days", "is_active", "updated_at"]
        read_only_fields = ["updated_at"]


class UserMembershipSerializer(serializers.ModelSerializer):
    is_currently_active = serializers.BooleanField(read_only=True)
    plan = MembershipPlanSerializer(read_only=True)

    class Meta:
        model = UserMembership
        fields = [
            "id", "plan", "status", "payment_reference",
            "start_date", "end_date", "is_currently_active",
            "created_at", "updated_at",
        ]
        read_only_fields = fields
