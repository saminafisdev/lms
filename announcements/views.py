from rest_framework import viewsets, mixins, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from config.permissions import IsAdminRole, IsAdminOrTeacher
from courses.models import Course, Enrollment
from .models import CourseAnnouncement, SiteAnnouncement
from .serializers import CourseAnnouncementSerializer, SiteAnnouncementSerializer


class CourseAnnouncementViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CourseAnnouncementSerializer

    def get_course(self):
        return Course.objects.get(pk=self.kwargs["course_pk"])

    def get_queryset(self):
        return CourseAnnouncement.objects.filter(
            course_id=self.kwargs["course_pk"]
        ).select_related("created_by")

    def get_permissions(self):
        if self.action in ("create", "destroy"):
            return [IsAdminOrTeacher()]
        # list: enrolled students, admin, teachers
        return [permissions.IsAuthenticated()]

    def check_list_permission(self, request, course):
        """Non-admin/teacher users must be enrolled to read announcements."""
        if request.user.role in ("admin", "teacher"):
            return True
        return Enrollment.objects.filter(user=request.user, course=course).exists()

    def list(self, request, *args, **kwargs):
        course = self.get_course()
        if not self.check_list_permission(request, course):
            return Response(
                {"detail": "You must be enrolled to view announcements."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        course = self.get_course()
        announcement = serializer.save(course=course, created_by=self.request.user)
        # Notify all enrolled students
        from notifications.utils import notify_bulk
        from courses.models import Enrollment
        enrolled_users = list(
            Enrollment.objects.filter(course=course).select_related("user").values_list("user", flat=True)
        )
        from accounts.models import User
        recipients = User.objects.filter(pk__in=enrolled_users)
        notify_bulk(
            recipients=recipients,
            notification_type="announcement",
            title=f"New announcement in {course.title}",
            message=announcement.title,
            link=f"/courses/{course.slug}/announcements/",
        )


class SiteAnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = SiteAnnouncementSerializer
    queryset = SiteAnnouncement.objects.all()

    def get_permissions(self):
        if self.action == "active":
            return [permissions.AllowAny()]
        return [IsAdminRole()]

    @extend_schema(responses={200: SiteAnnouncementSerializer})
    @action(detail=False, methods=["get"], url_path="active")
    def active(self, request):
        """Return the currently active site-wide announcement, or 204 if none."""
        announcement = SiteAnnouncement.objects.filter(is_active=True).first()
        if announcement is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(SiteAnnouncementSerializer(announcement).data)
