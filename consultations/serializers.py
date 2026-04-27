from rest_framework import serializers
from accounts.serializers import CourseTeacherSerializer
from .models import Consultation, AvailableTimeslot, Bundle, ConsultationPurchase, RecurringAvailability, RescheduleRequest


class RecurringAvailabilitySerializer(serializers.ModelSerializer):
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = RecurringAvailability
        fields = [
            "id", "consultation", "weekday", "weekday_display",
            "start_time", "end_time", "session_duration_minutes",
            "valid_from", "valid_until",
        ]
        read_only_fields = ["id", "weekday_display", "consultation"]


class AvailableTimeslotSerializer(serializers.ModelSerializer):
    zoom_start_url = serializers.SerializerMethodField()
    consultation_details = serializers.SerializerMethodField()

    class Meta:
        model = AvailableTimeslot
        fields = [
            "id", "consultation", "consultation_details", "recurring_rule",
            "scheduled_start", "scheduled_end", "is_booked",
            "zoom_meeting_id", "zoom_join_url", "zoom_start_url",
        ]
        read_only_fields = ["consultation", "zoom_meeting_id", "zoom_join_url", "zoom_start_url", "is_booked"]

    def get_zoom_start_url(self, obj):
        request = self.context.get("request")
        user = request.user if request else None
        if user and user.is_authenticated and (
            user.is_staff or getattr(user, "role", None) in ("admin", "teacher")
        ):
            return obj.zoom_start_url
        return None

    def get_consultation_details(self, obj):
        c = obj.consultation
        if not c:
            return None
        teacher = c.teacher
        teacher_data = None
        if teacher:
            teacher_data = {
                "id": teacher.id,
                "name": f"{teacher.user.first_name} {teacher.user.last_name}".strip() or teacher.user.email,
                "email": teacher.user.email,
                "profile_picture": self.context.get("request").build_absolute_uri(teacher.profile_picture.url)
                    if teacher.profile_picture and self.context.get("request") else (
                        teacher.profile_picture.url if teacher.profile_picture else None
                    ),
                "professional_title": teacher.professional_title,
                "about": teacher.about,
            }
        return {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "teacher": teacher_data,
        }


class ConsultationBundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bundle
        fields = "__all__"
        read_only_fields = ["consultation"]


class ConsultationSerializer(serializers.ModelSerializer):
    teacher = CourseTeacherSerializer(read_only=True)
    teacher_id = serializers.IntegerField(write_only=True)
    timeslots = AvailableTimeslotSerializer(many=True, read_only=True)
    bundles = ConsultationBundleSerializer(many=True, read_only=True)
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


class TimeslotSlimSerializer(serializers.ModelSerializer):
    """Minimal serializer for student-facing timeslot listing."""
    class Meta:
        model = AvailableTimeslot
        fields = ["id", "scheduled_start", "scheduled_end", "is_booked"]


class ConsultationBookSerializer(serializers.Serializer):
    timeslot_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)


class ConsultationPurchaseSerializer(serializers.ModelSerializer):
    """Detailed read serializer — used for admin views and student purchase history."""
    student_email = serializers.EmailField(source="student.email", read_only=True)
    student_name = serializers.SerializerMethodField()
    consultation_title = serializers.CharField(source="consultation.title", read_only=True)
    booked_slots = serializers.SerializerMethodField()

    def get_booked_slots(self, obj):
        return AvailableTimeslotSerializer(
            obj.booked_slots.all(),
            many=True,
            context=self.context,
        ).data
    bundle_applied = ConsultationBundleSerializer(read_only=True)

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


class RescheduleRequestSerializer(serializers.ModelSerializer):
    student_email = serializers.EmailField(source="purchase.student.email", read_only=True)
    old_slot_time = serializers.DateTimeField(source="old_slot.scheduled_start", read_only=True)
    requested_slot_time = serializers.DateTimeField(source="requested_slot.scheduled_start", read_only=True)

    class Meta:
        model = RescheduleRequest
        fields = [
            "id",
            "purchase",
            "old_slot",
            "old_slot_time",
            "requested_slot",
            "requested_slot_time",
            "status",
            "reason",
            "student_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "student_email", "old_slot_time", "requested_slot_time", "created_at", "updated_at"]
