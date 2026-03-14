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


class CourseSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    teacher = TeacherProfileSerializer(read_only=True)
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


class ScholarshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scholarship
        fields = "__all__"


class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = "__all__"


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = "__all__"


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = "__all__"


class QuestionSerializer(serializers.ModelSerializer):
    options = OptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = "__all__"


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = "__all__"


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = "__all__"
