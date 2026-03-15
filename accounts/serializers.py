from djoser.serializers import (
    UserCreateSerializer,
    UserSerializer,
    UserCreatePasswordRetypeSerializer,
)
from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import TeacherProfile, StudentProfile

User = get_user_model()


class TeacherProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.ReadOnlyField(source="user.email")

    class Meta:
        model = TeacherProfile
        fields = "__all__"


class StudentProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.ReadOnlyField(source="user.email")

    class Meta:
        model = StudentProfile
        fields = "__all__"


class CustomUserCreateSerializer(UserCreateSerializer):
    teacher_profile = TeacherProfileSerializer(required=False)
    student_profile = StudentProfileSerializer(required=False)

    class Meta(UserCreateSerializer.Meta):
        model = User
        fields = (
            "id",
            "email",
            "password",
            "role",
            "first_name",
            "last_name",
            "teacher_profile",
            "student_profile",
        )

    def create(self, validated_data):
        teacher_profile_data = validated_data.pop("teacher_profile", None)
        student_profile_data = validated_data.pop("student_profile", None)

        user = super().create(validated_data)

        # Signals will create the profile automatically, we just update it if data was provided
        if user.role == User.TEACHER and teacher_profile_data:
            profile, created = TeacherProfile.objects.get_or_create(user=user)
            for attr, value in teacher_profile_data.items():
                setattr(profile, attr, value)
            profile.save()
        elif user.role == User.STUDENT and student_profile_data:
            profile, created = StudentProfile.objects.get_or_create(user=user)
            for attr, value in student_profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        return user


class CustomUserCreatePasswordRetypeSerializer(UserCreatePasswordRetypeSerializer):
    teacher_profile = TeacherProfileSerializer(required=False)
    student_profile = StudentProfileSerializer(required=False)

    class Meta(UserCreatePasswordRetypeSerializer.Meta):
        model = User
        fields = (
            "id",
            "email",
            "password",
            "role",
            "first_name",
            "last_name",
            "teacher_profile",
            "student_profile",
        )

    def create(self, validated_data):
        teacher_profile_data = validated_data.pop("teacher_profile", None)
        student_profile_data = validated_data.pop("student_profile", None)

        user = super().create(validated_data)

        if user.role == User.TEACHER and teacher_profile_data:
            profile, created = TeacherProfile.objects.get_or_create(user=user)
            for attr, value in teacher_profile_data.items():
                setattr(profile, attr, value)
            profile.save()
        elif user.role == User.STUDENT and student_profile_data:
            profile, created = StudentProfile.objects.get_or_create(user=user)
            for attr, value in student_profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        return user


class CustomUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        model = User
        fields = ("id", "email", "role", "first_name", "last_name")
