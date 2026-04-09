from config.fields import RichTextField
from rest_framework import serializers
from accounts.serializers import TeacherProfileSerializer
from accounts.models import TeacherProfile
from .models import (
    CourseCategory,
    Course,
    Scholarship,
    Module,
    Lesson,
    Quiz,
    Question,
    Option,
    Assignment,
    Enrollment,
)


class CourseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseCategory
        fields = "__all__"


class ScholarshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scholarship
        fields = "__all__"


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

    class Meta:
        model = Lesson
        fields = "__all__"

    def get_is_accessible(self, obj):
        request = self.context.get("request")
        user = request.user if request else None

        if not user or not user.is_authenticated:
            return obj.is_preview
        if user.is_staff or user.role == "admin":
            return True
        if obj.module.course.teacher and obj.module.course.teacher.user == user:
            return True
        return (
            obj.is_preview
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

        return data


class ModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSerializer(many=True, read_only=True)
    total_lessons = serializers.IntegerField(source="lessons.count", read_only=True)
    total_duration = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = "__all__"
        extra_kwargs = {"course": {"required": False}}

    def get_total_duration(self, obj):
        return sum(lesson.duration_in_minutes for lesson in obj.lessons.all())


class CourseSerializer(serializers.ModelSerializer):
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
        return sum(module.lessons.count() for module in obj.modules.all())


class EnrollmentSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True)

    class Meta:
        model = Enrollment
        fields = "__all__"
