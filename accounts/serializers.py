from djoser.serializers import (
    UserCreateSerializer,
    UserSerializer,
    UserCreatePasswordRetypeSerializer,
)
from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import TeacherProfile, StudentProfile, NewsletterSubscriber

User = get_user_model()


# Custom User Create Serializer (handling user creation)
class CustomUserCreateSerializer(UserCreateSerializer):
    joined_at = serializers.DateTimeField(source="date_joined", read_only=True)

    class Meta(UserCreateSerializer.Meta):
        model = User
        fields = (
            "id",
            "email",
            "password",
            "role",
            "first_name",
            "last_name",
            "joined_at",
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
    joined_at = serializers.DateTimeField(source="date_joined", read_only=True)

    class Meta(UserSerializer.Meta):
        model = User
        fields = ("id", "email", "role", "first_name", "last_name", "joined_at")


class TeacherProfileUpdateUserSerializer(serializers.ModelSerializer):
    """Minimal user serializer for TeacherProfile updates — no password fields."""
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name")
        read_only_fields = ("id", "email")


class TeacherProfileSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer()
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

    def get_fields(self):
        fields = super().get_fields()
        # Use create serializer (with password) only on creation
        if self.instance is None:
            fields["user"] = CustomUserCreateSerializer()
        else:
            fields["user"] = TeacherProfileUpdateUserSerializer()
        return fields

    def get_courses(self, obj):
        from courses.serializers import CourseListSerializer
        return CourseListSerializer(
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
        user_data["role"] = User.TEACHER
        user = User.objects.create_user(**user_data)
        teacher_profile = user.teacher_profile
        for attr, value in validated_data.items():
            setattr(teacher_profile, attr, value)
        teacher_profile.save()
        return teacher_profile

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        if user_data:
            user = instance.user
            for attr, value in user_data.items():
                setattr(user, attr, value)
            user.save()
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


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
        fields = ["id", "user", "phone_number", "location", "profile_picture"]

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


class StudentProfileMeSerializer(serializers.ModelSerializer):
    """Used for GET/PATCH /student-profiles/me/ — only profile fields, no password."""
    first_name = serializers.CharField(source="user.first_name", required=False)
    last_name = serializers.CharField(source="user.last_name", required=False)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = StudentProfile
        fields = ["id", "email", "first_name", "last_name", "phone_number", "location", "profile_picture"]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        for attr, value in user_data.items():
            setattr(instance.user, attr, value)
        instance.user.save(update_fields=list(user_data.keys()) or None)
        return super().update(instance, validated_data)


class SimpleStudentSerializer(serializers.ModelSerializer):
    """Read-only student snapshot for nesting inside enrollment/scholarship/submission serializers."""
    id = serializers.IntegerField(source="user.id")
    email = serializers.EmailField(source="user.email")
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")

    class Meta:
        model = StudentProfile
        fields = ["id", "email", "first_name", "last_name", "phone_number", "location", "profile_picture"]
        read_only_fields = fields


class NewsletterSubscribeSerializer(serializers.Serializer):
    email = serializers.EmailField()


class NewsletterSubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscriber
        fields = ["id", "email", "subscribed_at", "is_active"]
        read_only_fields = fields
