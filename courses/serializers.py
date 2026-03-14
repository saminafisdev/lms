from rest_framework import serializers
from accounts.serializers import TeacherProfileSerializer
from accounts.models import TeacherProfile
from .models import (
    Category,
    Course,
    Scholarship,
    Module,
    Lesson,
    Quiz,
    Question,
    Option,
    Assignment,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
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

    class Meta:
        model = Lesson
        fields = "__all__"
        extra_kwargs = {"module": {"required": False}}


class ModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = "__all__"
        extra_kwargs = {"course": {"required": False}}


class CourseSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    teacher = TeacherProfileSerializer(read_only=True)
    modules = ModuleSerializer(many=True, read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
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

    class Meta:
        model = Course
        fields = "__all__"
