from config.fields import RichTextField
from config.mixins import SlugMixin
from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from accounts.serializers import CourseTeacherSerializer, SimpleStudentSerializer
from accounts.models import TeacherProfile
from .models import (
    CourseCategory,
    Course,
    Bundle,
    Scholarship,
    ScholarshipDocument,
    Module,
    Lesson,
    Quiz,
    Question,
    Option,
    Assignment,
    Enrollment,
    QuizAttempt,
    QuizAnswer,
    AssignmentSubmission,
)
from courses.models import Lesson as LessonModel


class CourseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseCategory
        fields = "__all__"


class ScholarshipDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScholarshipDocument
        fields = ["id", "file", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at"]


class ApproveScholarshipSerializer(serializers.Serializer):
    discount_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=1,
        max_value=100,
        help_text="Discount percentage to grant (1–100)",
    )


class RejectScholarshipSerializer(serializers.Serializer):
    rejection_note = serializers.CharField(required=False, allow_blank=True)


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = "__all__"
        extra_kwargs = {"question": {"required": False}}


class QuestionSerializer(serializers.ModelSerializer):
    options = OptionSerializer(many=True)

    class Meta:
        model = Question
        fields = "__all__"
        extra_kwargs = {"quiz": {"required": False}}

    def create(self, validated_data):
        options_data = validated_data.pop("options", [])
        question = Question.objects.create(**validated_data)
        for option_data in options_data:
            Option.objects.create(question=question, **option_data)
        return question


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, default=[])

    class Meta:
        model = Quiz
        fields = "__all__"
        extra_kwargs = {"lesson": {"required": False}}

    def create(self, validated_data):
        questions_data = validated_data.pop("questions", [])
        quiz = Quiz.objects.create(**validated_data)
        for question_data in questions_data:
            options_data = question_data.pop("options", [])
            question = Question.objects.create(quiz=quiz, **question_data)
            for option_data in options_data:
                Option.objects.create(question=question, **option_data)
        return quiz

    def update(self, instance, validated_data):
        validated_data.pop("questions", None)  # questions managed separately
        return super().update(instance, validated_data)


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = "__all__"
        extra_kwargs = {"lesson": {"read_only": True}}


class LessonSerializer(serializers.ModelSerializer):
    quiz_details = QuizSerializer(read_only=True)
    assignment_details = AssignmentSerializer(read_only=True)
    is_accessible = serializers.SerializerMethodField()
    live_status = serializers.SerializerMethodField()
    zoom_start_url = serializers.SerializerMethodField()
    bunny_embed_url = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = "__all__"
        extra_kwargs = {
            "order": {"read_only": True},
            "module": {"read_only": True},
            "bunny_video_id": {"read_only": True},
            "bunny_video_status": {"read_only": True},
            "video_content": {"read_only": True},
            "zoom_meeting_id": {"read_only": True},
            "zoom_host_email": {"read_only": True},
            "zoom_join_url": {"read_only": True},
        }

    def get_live_status(self, obj):
        """
        For live lessons only. Returns one of:
          - "locked":    more than 30 minutes before scheduled_at
          - "upcoming":  within 30 minutes before scheduled_at
          - "live":      class is currently in progress
          - "completed": class has ended
        Returns None for non-live lessons.
        """
        if obj.content_type != "live":
            return None
        if not obj.scheduled_at:
            return None

        now = timezone.now()
        duration = timedelta(minutes=obj.duration_in_minutes or 60)
        end_time = obj.scheduled_at + duration
        upcoming_window = obj.scheduled_at - timedelta(minutes=30)

        if now >= obj.scheduled_at and now <= end_time:
            return "live"
        if now > end_time:
            return "completed"
        if now >= upcoming_window:
            return "upcoming"
        return "locked"

    def get_zoom_start_url(self, obj):
        """Only expose the host start URL to admins and teachers."""
        request = self.context.get("request")
        user = request.user if request else None
        if not user or not user.is_authenticated:
            return None
        if user.is_staff or getattr(user, "role", None) == "admin":
            return obj.zoom_start_url
        if obj.module.course.teacher and obj.module.course.teacher.user == user:
            return obj.zoom_start_url
        return None

    def get_bunny_embed_url(self, obj):
        if not obj.bunny_video_id:
            return None
        library_id = settings.BUNNY_STREAM_LIBRARY_ID
        return (
            f"https://iframe.mediadelivery.net/embed/{library_id}/{obj.bunny_video_id}"
        )

    def _is_enrolled(self, obj, user):
        """Check enrollment via pre-fetched context or DB fallback."""
        enrolled_course_ids = self.context.get("enrolled_course_ids")
        has_active_membership = self.context.get("has_active_membership", False)
        if enrolled_course_ids is not None:
            return has_active_membership or (
                obj.module.course_id in enrolled_course_ids
            )
        has_membership = (
            hasattr(user, "membership") and user.membership.is_currently_active
        )
        return (
            has_membership
            or Enrollment.objects.filter(user=user, course=obj.module.course).exists()
        )

    def get_is_accessible(self, obj):
        request = self.context.get("request")
        user = request.user if request else None

        if not user or not user.is_authenticated:
            return obj.is_preview
        if user.is_staff or getattr(user, "role", None) == "admin":
            return True
        if obj.module.course.teacher and obj.module.course.teacher.user == user:
            return True

        if not self._is_enrolled(obj, user):
            return obj.is_preview

        # Enrolled student — check release state
        if obj.content_type == "live":
            return self.get_live_status(obj) in ("upcoming", "live", "completed")
        return obj.is_released

    def to_representation(self, instance):
        data = super().to_representation(instance)
        is_accessible = self.get_is_accessible(instance)
        live_status = self.get_live_status(instance)

        if not is_accessible:
            data["content"] = None
            data["file_content"] = None
            data["video_content"] = None
            data["quiz_details"] = None
            data["assignment_details"] = None
            data["zoom_join_url"] = None
            data["zoom_start_url"] = None
            data["bunny_embed_url"] = None
        elif live_status not in ("live", "upcoming"):
            # Accessible but not yet in the 30-min window — hide join URL
            data["zoom_join_url"] = None

        return data


class LiveLessonSerializer(serializers.ModelSerializer):
    """Used in teacher live-sessions list and dashboard upcoming sessions."""

    course_id = serializers.IntegerField(source="module.course.id", read_only=True)
    course_title = serializers.CharField(source="module.course.title", read_only=True)
    module_title = serializers.CharField(source="module.title", read_only=True)
    enrolled_count = serializers.SerializerMethodField()
    live_status = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            "id",
            "title",
            "course_id",
            "course_title",
            "module_title",
            "scheduled_at",
            "duration_in_minutes",
            "live_status",
            "enrolled_count",
            "zoom_meeting_id",
            "zoom_start_url",
            "zoom_join_url",
            "is_released",
        ]

    def get_enrolled_count(self, obj):
        return obj.module.course.enrollments.count()

    def get_live_status(self, obj):
        if not obj.scheduled_at:
            return None
        now = timezone.now()
        duration = timedelta(minutes=obj.duration_in_minutes or 60)
        end_time = obj.scheduled_at + duration
        if now >= obj.scheduled_at and now <= end_time:
            return "live"
        if now > end_time:
            return "completed"
        if now >= obj.scheduled_at - timedelta(minutes=30):
            return "upcoming"
        return "scheduled"


class ModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSerializer(many=True, read_only=True)
    total_lessons = serializers.SerializerMethodField()
    total_duration = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = "__all__"
        extra_kwargs = {
            "course": {"read_only": True},
            "order": {"read_only": True},
        }

    def get_total_lessons(self, obj):
        return len(list(obj.lessons.all()))

    def get_total_duration(self, obj):
        return sum(lesson.duration_in_minutes for lesson in obj.lessons.all())


class CourseListSerializer(SlugMixin, serializers.ModelSerializer):
    """Lightweight serializer for course list views — no nested modules/lessons."""

    category = CourseCategorySerializer(read_only=True)
    teacher = CourseTeacherSerializer(read_only=True)
    total_lessons = serializers.SerializerMethodField()
    is_enrolled = serializers.SerializerMethodField()
    has_access = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "thumbnail",
            "price",
            "level",
            "status",
            "is_active",
            "category",
            "teacher",
            "total_lessons",
            "duration_in_weeks",
            "total_hours",
            "hours_per_session",
            "is_enrolled",
            "has_access",
        ]

    def get_total_lessons(self, obj):
        if hasattr(obj, "total_lessons_count"):
            return obj.total_lessons_count
        return LessonModel.objects.filter(module__course=obj).count()

    def get_is_enrolled(self, obj):
        enrolled_course_ids = self.context.get("enrolled_course_ids")
        if enrolled_course_ids is not None:
            return obj.pk in enrolled_course_ids
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Enrollment.objects.filter(user=request.user, course=obj).exists()

    def get_has_access(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if self.context.get("has_active_membership", False):
            return True
        enrolled_course_ids = self.context.get("enrolled_course_ids")
        if enrolled_course_ids is not None:
            return obj.pk in enrolled_course_ids
        return Enrollment.objects.filter(user=request.user, course=obj).exists()


class CourseSerializer(SlugMixin, serializers.ModelSerializer):
    category = CourseCategorySerializer(read_only=True)
    teacher = CourseTeacherSerializer(read_only=True)
    modules = ModuleSerializer(many=True, read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=CourseCategory.objects.all(),
        source="category",
        write_only=True,
        required=False,
        allow_null=True,
    )
    teacher_id = serializers.PrimaryKeyRelatedField(
        queryset=TeacherProfile.objects.select_related("user").all(),
        source="teacher",
        write_only=True,
        required=False,
        allow_null=True,
    )
    total_lessons = serializers.SerializerMethodField()
    description = RichTextField()
    is_enrolled = serializers.SerializerMethodField()
    has_access = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = "__all__"

    def get_total_lessons(self, obj):
        if hasattr(obj, "total_lessons_count"):
            return obj.total_lessons_count
        return LessonModel.objects.filter(module__course=obj).count()

    def get_is_enrolled(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Enrollment.objects.filter(user=request.user, course=obj).exists()

    def get_has_access(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        has_membership = (
            hasattr(request.user, "membership")
            and request.user.membership.is_currently_active
        )
        if has_membership:
            return True
        return Enrollment.objects.filter(user=request.user, course=obj).exists()


class SimpleCourseSerializer(serializers.ModelSerializer):
    teacher = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ["id", "title", "thumbnail", "price", "level", "status", "teacher"]

    def get_teacher(self, obj):
        if not obj.teacher:
            return None
        profile = obj.teacher
        user = profile.user
        return {
            "id": profile.id,
            "full_name": user.get_full_name(),
            "profile_picture": (
                profile.profile_picture.url if profile.profile_picture else None
            ),
            "professional_title": profile.professional_title,
        }


class BundleCourseSerializer(serializers.ModelSerializer):
    """Minimal course serializer used inside Bundle responses."""

    category = CourseCategorySerializer(read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "thumbnail",
            "price",
            "level",
            "status",
            "category",
        ]


class BundleSerializer(serializers.ModelSerializer):
    courses_detail = BundleCourseSerializer(source="courses", many=True, read_only=True)
    course_ids = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(),
        source="courses",
        many=True,
        write_only=True,
        required=False,
    )
    original_price = serializers.SerializerMethodField()

    class Meta:
        model = Bundle
        fields = [
            "id",
            "name",
            "description",
            "price",
            "original_price",
            "courses_detail",
            "course_ids",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_original_price(self, obj):
        return sum(c.price for c in obj.courses.all())


class ScholarshipSerializer(serializers.ModelSerializer):
    course_detail = SimpleCourseSerializer(source="course", read_only=True)
    user_detail = SimpleStudentSerializer(source="user.student_profile", read_only=True)
    reviewed_by_detail = serializers.SerializerMethodField()
    documents = ScholarshipDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Scholarship
        fields = "__all__"
        read_only_fields = [
            "user",
            "status",
            "discount_percent",
            "rejection_note",
            "reviewed_by",
            "reviewed_at",
            "created_at",
        ]

    def get_reviewed_by_detail(self, obj):
        if not obj.reviewed_by:
            return None
        u = obj.reviewed_by
        return {
            "id": u.id,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
        }


class EnrollmentSerializer(serializers.ModelSerializer):
    course = SimpleCourseSerializer(read_only=True)
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(),
        source="course",
        write_only=True,
    )
    student = SimpleStudentSerializer(source="user.student_profile", read_only=True)

    class Meta:
        model = Enrollment
        fields = "__all__"
        read_only_fields = ["user", "enrolled_at"]


# ── Quiz Submission ──────────────────────────────────────────────────────────


class QuizAnswerSubmitSerializer(serializers.Serializer):
    question = serializers.PrimaryKeyRelatedField(queryset=Question.objects.all())
    selected_option = serializers.PrimaryKeyRelatedField(queryset=Option.objects.all())

    def validate(self, data):
        if data["selected_option"].question_id != data["question"].id:
            raise serializers.ValidationError(
                "selected_option does not belong to the given question."
            )
        return data


class QuizSubmitSerializer(serializers.Serializer):
    answers = QuizAnswerSubmitSerializer(many=True)

    def validate_answers(self, value):
        if not value:
            raise serializers.ValidationError("At least one answer is required.")
        return value


class QuizAttemptResultSerializer(serializers.ModelSerializer):
    passing_score = serializers.SerializerMethodField()
    total_questions = serializers.SerializerMethodField()

    class Meta:
        model = QuizAttempt
        fields = [
            "id",
            "score",
            "passed",
            "passing_score",
            "total_questions",
            "created_at",
        ]

    def get_passing_score(self, obj):
        return obj.quiz.passing_score

    def get_total_questions(self, obj):
        return obj.quiz.questions.count()


class QuizAttemptListSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizAttempt
        fields = ["id", "score", "passed", "created_at"]


# ── Assignment Submission ────────────────────────────────────────────────────


class AssignmentSubmissionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentSubmission
        fields = ["submission_text", "submission_file"]

    def validate(self, data):
        if not data.get("submission_text") and not data.get("submission_file"):
            raise serializers.ValidationError(
                "Provide either submission_text or submission_file."
            )
        return data


class AssignmentSubmissionReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentSubmission
        fields = ["status", "teacher_feedback", "mark"]

    def validate_status(self, value):
        allowed = [
            AssignmentSubmission.Status.APPROVED,
            AssignmentSubmission.Status.REJECTED,
        ]
        if value not in allowed:
            raise serializers.ValidationError(
                "Status must be 'approved' or 'rejected'."
            )
        return value


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    user_detail = SimpleStudentSerializer(source="user.student_profile", read_only=True)
    reviewed_by_detail = serializers.SerializerMethodField()
    assignment_title = serializers.CharField(
        source="assignment.lesson.title", read_only=True
    )

    class Meta:
        model = AssignmentSubmission
        fields = [
            "id",
            "user_detail",
            "assignment",
            "assignment_title",
            "submission_text",
            "submission_file",
            "status",
            "teacher_feedback",
            "mark",
            "reviewed_by_detail",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]

    def get_reviewed_by_detail(self, obj):
        if not obj.reviewed_by:
            return None
        u = obj.reviewed_by
        return {
            "id": u.id,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
        }
