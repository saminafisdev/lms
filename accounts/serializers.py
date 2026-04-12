from djoser.serializers import (
    UserCreateSerializer,
    UserSerializer,
    UserCreatePasswordRetypeSerializer,
)
from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import TeacherProfile, StudentProfile

User = get_user_model()


# Custom User Create Serializer (handling user creation)
class CustomUserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        model = User
        fields = (
            "id",
            "email",
            "password",
            "role",
            "first_name",
            "last_name",
        )
        extra_kwargs = {"role": {"read_only": True}}


# Custom User Create with Password Retype Serializer
class CustomUserCreatePasswordRetypeSerializer(UserCreatePasswordRetypeSerializer):
    class Meta(UserCreatePasswordRetypeSerializer.Meta):
        model = User
        fields = (
            "id",
            "email",
            "password",
            "role",
            "first_name",
            "last_name",
        )
        extra_kwargs = {"role": {"read_only": True}}


# Custom User Serializer (for reading User data)
class CustomUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        model = User
        fields = ("id", "email", "role", "first_name", "last_name")


class TeacherProfileSerializer(serializers.ModelSerializer):
    user = CustomUserCreateSerializer()
    courses = serializers.SerializerMethodField()
    consultations = serializers.SerializerMethodField()

    class Meta:
        model = TeacherProfile
        fields = [
            "id",
            "user",
            "profile_picture",
            "professional_title",
            "location",
            "about",
            "education",
            "achievements",
            "consultation_rate",
            "offers_consultations",
            "courses",
            "consultations",
        ]

    def get_courses(self, obj):
        from courses.serializers import SimpleCourseSerializer
        return SimpleCourseSerializer(
            obj.courses.filter(is_active=True), many=True, context=self.context
        ).data

    def get_consultations(self, obj):
        from consultations.serializers import ConsultationSerializer
        return ConsultationSerializer(
            obj.consultations.prefetch_related("timeslots", "bundles"),
            many=True,
            context=self.context,
        ).data

    def create(self, validated_data):
        user_data = validated_data.pop("user")

        # Manually set the role to teacher
        user_data["role"] = User.TEACHER

        # Signal will auto-create the profile, so just create the user
        user = User.objects.create_user(**user_data)

        # Update the profile created by the signal with the remaining fields
        teacher_profile = user.teacher_profile
        for attr, value in validated_data.items():
            setattr(teacher_profile, attr, value)
        teacher_profile.save()

        return teacher_profile


class CourseTeacherSerializer(serializers.ModelSerializer):
    """
    Minimal teacher serializer for embedding inside Course responses.
    No nested courses or consultations — avoids circular/deep nesting.
    """
    user = CustomUserSerializer()

    class Meta:
        model = TeacherProfile
        fields = [
            "id",
            "user",
            "profile_picture",
            "professional_title",
            "location",
            "about",
            "consultation_rate",
            "offers_consultations",
        ]


class StudentProfileSerializer(serializers.ModelSerializer):
    user = CustomUserCreateSerializer()

    class Meta:
        model = StudentProfile
        fields = ["id", "user"]

    def create(self, validated_data):
        user_data = validated_data.pop("user")

        # Manually set the role to student
        user_data["role"] = User.STUDENT

        # Signal will auto-create the profile, so just create the user
        user = User.objects.create_user(**user_data)

        # Update the profile created by the signal with the remaining fields
        student_profile = user.student_profile
        for attr, value in validated_data.items():
            setattr(student_profile, attr, value)
        student_profile.save()

        return student_profile
