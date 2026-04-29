from django.db.models import Q
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import Blog, BlogCategory
from .serializers import (
    BlogCategorySerializer,
    AdminBlogSerializer,
    TeacherBlogSerializer,
    PublicBlogSerializer,
    ApproveRejectSerializer,
)
from .permissions import IsAdminRole, IsAdminOrAuthor, IsTeacherOrAdmin


class BlogCategoryViewSet(viewsets.ModelViewSet):
    queryset = BlogCategory.objects.all()
    serializer_class = BlogCategorySerializer
    lookup_field = "slug"
    pagination_class = None

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        return [IsAdminRole()]


@extend_schema_view(
    list=extend_schema(responses={200: PublicBlogSerializer}),
    retrieve=extend_schema(responses={200: PublicBlogSerializer}),
    create=extend_schema(request=TeacherBlogSerializer, responses={201: TeacherBlogSerializer}),
    update=extend_schema(request=AdminBlogSerializer, responses={200: AdminBlogSerializer}),
    partial_update=extend_schema(request=AdminBlogSerializer, responses={200: AdminBlogSerializer}),
)
class BlogViewSet(viewsets.ModelViewSet):
    """
    ViewSet for blogs.
    - Public: list and retrieve published blogs.
    - Teacher: create, edit own blogs, view own blogs via my_blogs.
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
            return Blog.objects.none()

        if user.is_authenticated and user.role == "admin":
            return Blog.objects.all()

        # my_blogs action — handled separately
        if self.action == "my_blogs":
            return Blog.objects.none()  # overridden in the action

        return Blog.objects.filter(status=Blog.STATUS_PUBLISHED)

    def get_serializer_class(self):
        if getattr(self, "swagger_fake_view", False):
            return AdminBlogSerializer

        user = self.request.user

        if user.is_authenticated and user.role == "admin":
            return AdminBlogSerializer

        if self.action in ["create", "update", "partial_update"]:
            return TeacherBlogSerializer

        return PublicBlogSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        if self.action == "create":
            return [IsTeacherOrAdmin()]
        if self.action in ["update", "partial_update", "destroy"]:
            return [IsAdminOrAuthor()]
        if self.action in ["approve", "reject"]:
            return [IsAdminRole()]
        if self.action == "my_blogs":
            return [IsTeacherOrAdmin()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user
        teacher_profile = getattr(user, "teacher_profile", None)

        # Admin without a TeacherProfile cannot author blogs
        if teacher_profile is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                "You need a teacher profile to author blogs. Contact the platform owner."
            )

        # Admins publish directly, teachers go to pending
        initial_status = (
            Blog.STATUS_PUBLISHED if user.role == "admin" else Blog.STATUS_PENDING
        )
        serializer.save(author=teacher_profile, status=initial_status)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Increment view count on retrieve for public users
        if not request.user.is_authenticated or request.user.role != "admin":
            Blog.objects.filter(pk=instance.pk).update(view_count=instance.view_count + 1)
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Related blogs: same category, published, excluding self, up to 4
        related_qs = Blog.objects.filter(
            category=instance.category,
            status=Blog.STATUS_PUBLISHED,
        ).exclude(pk=instance.pk).select_related("category", "author", "author__user").order_by("-published_at")[:4]
        data["related_blogs"] = PublicBlogSerializer(
            related_qs, many=True, context=self.get_serializer_context()
        ).data

        return Response(data)

    @extend_schema(
        summary="List teacher's own blogs",
        description="Returns all blogs authored by the authenticated teacher across all statuses.",
        parameters=[
            OpenApiParameter("search", OpenApiTypes.STR, description="Search in title, excerpt, and content."),
            OpenApiParameter("status", OpenApiTypes.STR, description="Filter by status: `draft`, `pending`, or `published`."),
            OpenApiParameter("category__slug", OpenApiTypes.STR, description="Filter by category slug."),
            OpenApiParameter("ordering", OpenApiTypes.STR, description="Order by `created_at`, `-created_at` (default), or `title`."),
        ],
        responses={200: TeacherBlogSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="my-blogs")
    def my_blogs(self, request):
        teacher_profile = getattr(request.user, "teacher_profile", None)
        if teacher_profile is None:
            return Response(
                {"detail": "No teacher profile found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        qs = Blog.objects.filter(author=teacher_profile)

        # Filter
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        category_slug = request.query_params.get("category__slug")
        if category_slug:
            qs = qs.filter(category__slug=category_slug)

        # Search
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(excerpt__icontains=search) |
                Q(content__icontains=search)            )

        # Ordering
        ordering = request.query_params.get("ordering", "-created_at")
        if ordering.lstrip("-") in ("created_at", "title"):
            qs = qs.order_by(ordering)

        serializer = TeacherBlogSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, slug=None):
        """Approve a pending blog — admin only."""
        blog = self.get_object()
        if blog.status == Blog.STATUS_PUBLISHED:
            return Response(
                {"detail": "Blog is already published."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        blog.status = Blog.STATUS_PUBLISHED
        blog.rejection_reason = None
        blog.save()
        return Response({"detail": "Blog approved and published."})

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, slug=None):
        """Reject a pending blog with an optional reason — admin only."""
        blog = self.get_object()
        serializer = ApproveRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        blog.status = Blog.STATUS_REJECTED
        blog.rejection_reason = serializer.validated_data.get("reason", "")
        blog.save()
        return Response({"detail": "Blog rejected."})

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, slug=None):
        """
        Teacher submits a draft for approval.
        Changes status from draft → pending.
        """
        blog = self.get_object()
        teacher_profile = getattr(request.user, "teacher_profile", None)

        if blog.author != teacher_profile:
            return Response(
                {"detail": "You can only submit your own blogs."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if blog.status != Blog.STATUS_DRAFT:
            return Response(
                {"detail": "Only draft blogs can be submitted for approval."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        blog.status = Blog.STATUS_PENDING
        blog.save()
        return Response({"detail": "Blog submitted for approval."})