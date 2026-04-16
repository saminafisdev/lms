import json
from rest_framework import permissions
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.sendgrid_contacts import add_contact, remove_contact

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

    def _coerce_data(self, request):
        """
        For multipart requests, the nested `user` object must be sent as a
        JSON string (e.g. user='{"email":...}'). This method parses it so the
        serializer receives a proper dict.
        JSON/application-json requests are passed through unchanged.
        """
        if not hasattr(request.data, 'getlist'):
            # Already a plain dict (JSON request) — pass through unchanged
            return request.data

        # Build a plain Python dict from QueryDict, preserving lists
        data = {}
        for key in request.data.keys():
            values = request.data.getlist(key)
            data[key] = values if len(values) > 1 else values[0]

        if isinstance(data.get("user"), str):
            try:
                data["user"] = json.loads(data["user"])
            except json.JSONDecodeError:
                pass
        return data

    def create(self, request, *args, **kwargs):
        data = self._coerce_data(request)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        data = self._coerce_data(request)
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

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
