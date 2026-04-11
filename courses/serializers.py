from config.fields import RichTextField
from config.mixins import SlugMixin
from rest_framework import serializers
from accounts.serializers import TeacherProfileSerializer
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
    options = OptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = "__all__"
        extra_kwargs = {"quiz": {"required": False}}


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = "__all__"
        extra_kwargs = {"lesson": {"required": False}}


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = "__all__"
        extra_kwargs = {"lesson": {"required": False}}


class LessonSerializer(serializers.ModelSerializer):
    quiz_details = QuizSerializer(read_only=True)
    assignment_details = AssignmentSerializer(read_only=True)
    is_accessible = serializers.SerializerMethodField()
    zoom_start_url = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = "__all__"

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

    def get_is_accessible(self, obj):
        request = self.context.get("request")
        user = request.user if request else None

        if not user or not user.is_authenticated:
            return obj.is_preview
        if user.is_staff or getattr(user, "role", None) == "admin":
            return True
        if obj.module.course.teacher and obj.module.course.teacher.user == user:
            return True

        # Use pre-fetched enrollment set from context (avoids N+1)
        enrolled_course_ids = self.context.get("enrolled_course_ids")
        has_active_membership = self.context.get("has_active_membership", False)
        if enrolled_course_ids is not None:
            return obj.is_preview or has_active_membership or (obj.module.course_id in enrolled_course_ids)

        # Fallback for contexts without pre-fetched enrollments
        has_membership = hasattr(user, 'membership') and user.membership.is_currently_active
        return (
            obj.is_preview
            or has_membership
            or Enrollment.objects.filter(user=user, course=obj.module.course).exists()
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        is_accessible = self.get_is_accessible(instance)

        if not is_accessible:
            # keep metadata, strip actual content
            data["content"] = None
            data["file_content"] = None
            data["video_content"] = None
            data["quiz_details"] = None
            data["assignment_details"] = None
            data["zoom_join_url"] = None
            data["zoom_start_url"] = None

        return data


class ModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSerializer(many=True, read_only=True)
    total_lessons = serializers.SerializerMethodField()
    total_duration = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = "__all__"
        extra_kwargs = {"course": {"required": False}}

    def get_total_lessons(self, obj):
        return len(list(obj.lessons.all()))

    def get_total_duration(self, obj):
        return sum(lesson.duration_in_minutes for lesson in obj.lessons.all())


class CourseListSerializer(SlugMixin, serializers.ModelSerializer):
    """Lightweight serializer for course list views — no nested modules/lessons."""
    category = CourseCategorySerializer(read_only=True)
    teacher = TeacherProfileSerializer(read_only=True)
    total_lessons = serializers.SerializerMethodField()
    is_enrolled = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id", "title", "slug", "thumbnail", "price", "level", "status",
            "is_active", "category", "teacher", "total_lessons", "is_enrolled",
            "created_at", "updated_at",
        ]

    def get_total_lessons(self, obj):
        if hasattr(obj, 'total_lessons_count'):
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


class CourseSerializer(SlugMixin, serializers.ModelSerializer):
    category = CourseCategorySerializer(read_only=True)
    teacher = TeacherProfileSerializer(read_only=True)
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

    class Meta:
        model = Course
        fields = "__all__"

    def get_total_lessons(self, obj):
        if hasattr(obj, 'total_lessons_count'):
            return obj.total_lessons_count
        return LessonModel.objects.filter(module__course=obj).count()


class SimpleCourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "title", "thumbnail", "price", "level", "status"]


class BundleCourseSerializer(serializers.ModelSerializer):
    """Minimal course serializer used inside Bundle responses."""
    category = CourseCategorySerializer(read_only=True)

    class Meta:
        model = Course
        fields = ["id", "title", "slug", "thumbnail", "price", "level", "status", "category"]


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
    user_detail = serializers.SerializerMethodField()
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

    def get_user_detail(self, obj):
        if not obj.user:
            return None
        u = obj.user
        return {"id": u.id, "email": u.email, "first_name": u.first_name, "last_name": u.last_name}

    def get_reviewed_by_detail(self, obj):
        if not obj.reviewed_by:
            return None
        u = obj.reviewed_by
        return {"id": u.id, "email": u.email, "first_name": u.first_name, "last_name": u.last_name}


class EnrollmentSerializer(serializers.ModelSerializer):
    course = SimpleCourseSerializer(read_only=True)

    class Meta:
        model = Enrollment
        fields = "__all__"
