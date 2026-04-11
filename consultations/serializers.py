from rest_framework import serializers
from accounts.serializers import TeacherProfileSerializer
from .models import Consultation, AvailableTimeslot, Bundle, ConsultationPurchase


class AvailableTimeslotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailableTimeslot
        fields = "__all__"


class BundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bundle
        fields = "__all__"


class ConsultationSerializer(serializers.ModelSerializer):
    teacher = TeacherProfileSerializer(read_only=True)
    teacher_id = serializers.IntegerField(write_only=True)
    timeslots = AvailableTimeslotSerializer(many=True, read_only=True)
    bundles = BundleSerializer(many=True, read_only=True)

    class Meta:
        model = Consultation
        fields = "__all__"


class ConsultationPurchaseSerializer(serializers.ModelSerializer):
    """Detailed read serializer — used for admin views and student purchase history."""
    student_email = serializers.EmailField(source="student.email", read_only=True)
    student_name = serializers.SerializerMethodField()
    consultation_title = serializers.CharField(source="consultation.title", read_only=True)
    booked_slots = AvailableTimeslotSerializer(many=True, read_only=True)
    bundle_applied = BundleSerializer(read_only=True)

    class Meta:
        model = ConsultationPurchase
        fields = [
            "id",
            "student",
            "student_email",
            "student_name",
            "consultation",
            "consultation_title",
            "bundle_applied",
            "total_price_paid",
            "sessions_purchased",
            "status",
            "payment_reference",
            "booked_slots",
            "created_at",
        ]
        read_only_fields = fields

    def get_student_name(self, obj):
        return (
            f"{obj.student.first_name} {obj.student.last_name}".strip()
            or obj.student.email
        )
