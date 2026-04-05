from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from .models import Video, VideoCategory
from .serializers import (
    VideoCategorySerializer,
    AdminVideoSerializer,
    TeacherVideoSerializer,
    PublicVideoSerializer,
    ApproveRejectSerializer,
)
from .permissions import IsAdminRole, IsAdminOrAuthor, IsTeacherOrAdmin


class VideoCategoryViewSet(viewsets.ModelViewSet):
    queryset = VideoCategory.objects.all()
    serializer_class = VideoCategorySerializer
    lookup_field = "slug"
    pagination_class = None

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        return [IsAdminRole()]


@extend_schema_view(
    list=extend_schema(responses={200: PublicVideoSerializer}),
    retrieve=extend_schema(responses={200: PublicVideoSerializer}),
    create=extend_schema(request=TeacherVideoSerializer, responses={201: TeacherVideoSerializer}),
    update=extend_schema(request=AdminVideoSerializer, responses={200: AdminVideoSerializer}),
    partial_update=extend_schema(request=AdminVideoSerializer, responses={200: AdminVideoSerializer}),
)
class VideoViewSet(viewsets.ModelViewSet):
    """
    ViewSet for video content.
    - Public: list and retrieve published videos.
    - Teacher: create, edit own videos, view own videos via my_videos.
    - Admin: full CRUD, approve/reject.
    """
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category__slug", "status"]
    search_fields = ["title", "excerpt", "content"]
    ordering_fields = ["published_at", "created_at", "view_count"]

    def get_queryset(self):
        user = self.request.user

        if getattr(self, "swagger_fake_view", False):
            return Video.objects.none()

        if user.is_authenticated and user.role == "admin":
            return Video.objects.all()

        # my_videos action — handled separately
        if self.action == "my_videos":
            return Video.objects.none()

        return Video.objects.filter(status=Video.STATUS_PUBLISHED)

    def get_serializer_class(self):
        if getattr(self, "swagger_fake_view", False):
            return AdminVideoSerializer

        user = self.request.user

        if user.is_authenticated and user.role == "admin":
            return AdminVideoSerializer

        if self.action in ["create", "update", "partial_update"]:
            return TeacherVideoSerializer

        return PublicVideoSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        if self.action == "create":
            return [IsTeacherOrAdmin()]
        if self.action in ["update", "partial_update", "destroy"]:
            return [IsAdminOrAuthor()]
        if self.action in ["approve", "reject"]:
            return [IsAdminRole()]
        if self.action == "my_videos":
            return [IsTeacherOrAdmin()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user
        teacher_profile = getattr(user, "teacher_profile", None)

        if teacher_profile is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                "You need a teacher profile to author videos. Contact the platform owner."
            )

        initial_status = (
            Video.STATUS_PUBLISHED if user.role == "admin" else Video.STATUS_PENDING
        )
        serializer.save(author=teacher_profile, status=initial_status)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.is_authenticated or request.user.role != "admin":
            Video.objects.filter(pk=instance.pk).update(view_count=instance.view_count + 1)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="my-videos")
    def my_videos(self, request):
        """Returns all videos authored by the current teacher — all statuses."""
        teacher_profile = getattr(request.user, "teacher_profile", None)
        if teacher_profile is None:
            return Response(
                {"detail": "No teacher profile found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        videos = Video.objects.filter(author=teacher_profile)
        serializer = TeacherVideoSerializer(videos, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, slug=None):
        """Approve a pending video — admin only."""
        video = self.get_object()
        if video.status == Video.STATUS_PUBLISHED:
            return Response(
                {"detail": "Video is already published."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        video.status = Video.STATUS_PUBLISHED
        video.rejection_reason = None
        video.save()
        return Response({"detail": "Video approved and published."})

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, slug=None):
        """Reject a pending video with an optional reason — admin only."""
        video = self.get_object()
        serializer = ApproveRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        video.status = Video.STATUS_REJECTED
        video.rejection_reason = serializer.validated_data.get("reason", "")
        video.save()
        return Response({"detail": "Video rejected."})

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, slug=None):
        """Teacher submits a draft for approval."""
        video = self.get_object()
        teacher_profile = getattr(request.user, "teacher_profile", None)

        if video.author != teacher_profile:
            return Response(
                {"detail": "You can only submit your own videos."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if video.status != Video.STATUS_DRAFT:
            return Response(
                {"detail": "Only draft videos can be submitted for approval."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        video.status = Video.STATUS_PENDING
        video.save()
        return Response({"detail": "Video submitted for approval."})
