from rest_framework import permissions
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

from config.sendgrid_contacts import add_contact, remove_contact
from config.permissions import IsAdminRole

from .models import StudentProfile, TeacherProfile
from .permissions import IsTeacher
from .serializers import (
    StudentProfileSerializer,
    TeacherProfileSerializer,
)


class TeacherProfileViewSet(viewsets.ModelViewSet):
    queryset = TeacherProfile.objects.all()
    serializer_class = TeacherProfileSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["professional_title", "location", "offers_consultations"]
    search_fields = [
        "user__first_name",
        "user__last_name",
        "user__email",
        "professional_title",
        "location",
        "about",
    ]

    def get_parsers(self):
        # create requires JSON (nested user object can't be represented in multipart)
        # update/partial_update allow multipart for profile picture uploads
        if self.action == "create":
            return [JSONParser()]
        return [MultiPartParser(), FormParser(), JSONParser()]

    def get_permissions(self):
        if self.action == "destroy":
            return [IsAdminRole()]
        return [permissions.AllowAny()]

    def perform_destroy(self, instance):
        # Deleting the user cascades and removes the teacher profile too
        instance.user.delete()

    @action(
        detail=False,
        methods=["get"],
        url_path="me",
        permission_classes=[IsAuthenticated, IsTeacher],
    )
    def me(self, request):
        try:
            teacher = request.user.teacher_profile
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(teacher)
        return Response(serializer.data)


class StudentProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.all()
    serializer_class = StudentProfileSerializer
    # permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        profile = serializer.save()
        if profile.is_subscribed_to_newsletter:
            add_contact(profile.user)

    def perform_update(self, serializer):
        old_subscribed = self.get_object().is_subscribed_to_newsletter
        profile = serializer.save()
        new_subscribed = profile.is_subscribed_to_newsletter

        if not old_subscribed and new_subscribed:
            add_contact(profile.user)
        elif old_subscribed and not new_subscribed:
            remove_contact(profile.user)

    @action(
        detail=False,
        methods=["post"],
        url_path="newsletter/subscribe",
        permission_classes=[permissions.IsAuthenticated],
    )
    def newsletter_subscribe(self, request):
        profile = getattr(request.user, "student_profile", None)
        if not profile:
            return Response(
                {"error": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        profile.is_subscribed_to_newsletter = True
        profile.save(update_fields=["is_subscribed_to_newsletter"])
        add_contact(request.user)
        return Response({"detail": "Subscribed to newsletter."})

    @action(
        detail=False,
        methods=["post"],
        url_path="newsletter/unsubscribe",
        permission_classes=[permissions.IsAuthenticated],
    )
    def newsletter_unsubscribe(self, request):
        profile = getattr(request.user, "student_profile", None)
        if not profile:
            return Response(
                {"error": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        profile.is_subscribed_to_newsletter = False
        profile.save(update_fields=["is_subscribed_to_newsletter"])
        remove_contact(request.user)
        return Response({"detail": "Unsubscribed from newsletter."})
