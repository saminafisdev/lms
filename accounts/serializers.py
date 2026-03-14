from djoser.serializers import (
    UserCreateSerializer,
    UserSerializer,
    UserCreatePasswordRetypeSerializer,
)
from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import TeacherProfile, StudentProfile

User = get_user_model()


class CustomUserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        model = User
        fields = ("id", "email", "password", "role")


class CustomUserCreatePasswordRetypeSerializer(UserCreatePasswordRetypeSerializer):
    class Meta(UserCreatePasswordRetypeSerializer.Meta):
        model = User
        fields = ("id", "email", "password", "role")


class CustomUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        model = User
        fields = ("id", "email", "role")


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
