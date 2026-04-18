from rest_framework import serializers
from accounts.serializers import CourseTeacherSerializer
from .models import Consultation, AvailableTimeslot, Bundle, ConsultationPurchase, RecurringAvailability


class RecurringAvailabilitySerializer(serializers.ModelSerializer):
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = RecurringAvailability
        fields = [
            "id", "consultation", "weekday", "weekday_display",
            "start_time", "end_time", "session_duration_minutes",
            "valid_from", "valid_until",
        ]
        read_only_fields = ["id", "weekday_display"]


class AvailableTimeslotSerializer(serializers.ModelSerializer):
    zoom_start_url = serializers.SerializerMethodField()

    class Meta:
        model = AvailableTimeslot
        fields = "__all__"

    def get_zoom_start_url(self, obj):
        request = self.context.get("request")
        user = request.user if request else None
        if user and user.is_authenticated and (
            user.is_staff or getattr(user, "role", None) in ("admin", "teacher")
        ):
            return obj.zoom_start_url
        return None


class BundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bundle
        fields = "__all__"


class ConsultationSerializer(serializers.ModelSerializer):
    teacher = CourseTeacherSerializer(read_only=True)
    teacher_id = serializers.IntegerField(write_only=True)
    timeslots = AvailableTimeslotSerializer(many=True, read_only=True)
    bundles = BundleSerializer(many=True, read_only=True)
    recurring_rules = RecurringAvailabilitySerializer(many=True, read_only=True)

    class Meta:
        model = Consultation
        fields = "__all__"

    def validate_teacher_id(self, value):
        from accounts.models import TeacherProfile
        try:
            teacher = TeacherProfile.objects.get(pk=value)
        except TeacherProfile.DoesNotExist:
            raise serializers.ValidationError("Teacher not found.")
        if not teacher.offers_consultations:
            raise serializers.ValidationError(
                "This teacher does not offer consultations. "
                "Enable 'offers_consultation' on their profile first."
            )
        return value


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
