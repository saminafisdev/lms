import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from config.permissions import IsAdminRole
from courses.models import Course, Enrollment
from .models import Post, Reply
from .serializers import PostSerializer, PostDetailSerializer, ReplySerializer

logger = logging.getLogger(__name__)


def _get_course(kwargs):
    return get_object_or_404(Course, pk=kwargs["course_pk"])


def _can_access_course(user, course):
    """Enrolled, active membership, teacher of course, or admin."""
    if not user.is_authenticated:
        return False
    if user.role == "admin" or user.is_staff:
        return True
    if course.teacher and course.teacher.user == user:
        return True
    if Enrollment.objects.filter(user=user, course=course).exists():
        return True
    return hasattr(user, "membership") and user.membership.is_currently_active


_POST_ACCESS_NOTE = (
    "**Access:** Enrolled students, the course teacher, active membership holders, and admins."
)
_ADMIN_ONLY_NOTE = "**Permissions:** Admin only."
_OWN_OR_ADMIN_NOTE = "**Permissions:** Author of the post, or admin."


@extend_schema_view(
    list=extend_schema(
        summary="List discussion posts",
        description=(
            "Returns all discussion posts for the given course, ordered by pinned-first then newest.\n\n"
            + _POST_ACCESS_NOTE
        ),
        responses={
            200: PostSerializer(many=True),
            403: OpenApiResponse(description="Not enrolled / not authenticated."),
        },
        tags=["Discussions"],
    ),
    create=extend_schema(
        summary="Create a discussion post",
        description=(
            "Creates a new discussion post in the course.\n\n"
            "- `title` and `body` are required.\n"
            "- `author`, `course`, `is_pinned`, and `is_closed` are set automatically and cannot be supplied.\n\n"
            + _POST_ACCESS_NOTE
        ),
        request=PostSerializer,
        responses={
            201: PostSerializer,
            403: OpenApiResponse(description="Not enrolled / not authenticated."),
        },
        tags=["Discussions"],
    ),
    retrieve=extend_schema(
        summary="Retrieve a discussion post with replies",
        description=(
            "Returns a single post including its full reply tree (top-level replies with nested children).\n\n"
            + _POST_ACCESS_NOTE
        ),
        responses={
            200: PostDetailSerializer,
            403: OpenApiResponse(description="Not enrolled / not authenticated."),
            404: OpenApiResponse(description="Post not found."),
        },
        tags=["Discussions"],
    ),
    partial_update=extend_schema(
        summary="Edit a discussion post",
        description=(
            "Partially updates a post (PATCH). Only `title` and `body` can be changed.\n\n"
            + _OWN_OR_ADMIN_NOTE + "\n\n"
            "Editing is blocked if the discussion is closed (admins are exempt)."
        ),
        request=PostSerializer,
        responses={
            200: PostSerializer,
            403: OpenApiResponse(description="Not the author, or discussion is closed."),
            404: OpenApiResponse(description="Post not found."),
        },
        tags=["Discussions"],
    ),
    update=extend_schema(exclude=True),
    destroy=extend_schema(
        summary="Delete a discussion post",
        description=(
            "Permanently deletes a post and all its replies.\n\n"
            + _ADMIN_ONLY_NOTE
        ),
        responses={
            204: OpenApiResponse(description="Deleted successfully."),
            403: OpenApiResponse(description="Admin only."),
            404: OpenApiResponse(description="Post not found."),
        },
        tags=["Discussions"],
    ),
)
class PostViewSet(viewsets.ModelViewSet):

    def get_queryset(self):
        course = _get_course(self.kwargs)
        return Post.objects.filter(course=course).select_related("author").prefetch_related("replies")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PostDetailSerializer
        return PostSerializer

    def get_permissions(self):
        if self.action in ("pin", "close", "destroy"):
            return [IsAdminRole()]
        return [permissions.IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        course = _get_course(self.kwargs)
        if not _can_access_course(request.user, course):
            return Response({"detail": "You must be enrolled to view discussions."}, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        course = _get_course(self.kwargs)
        if not _can_access_course(request.user, course):
            return Response({"detail": "You must be enrolled to view discussions."}, status=status.HTTP_403_FORBIDDEN)
        return super().retrieve(request, *args, **kwargs)

    def perform_create(self, serializer):
        course = _get_course(self.kwargs)
        if not _can_access_course(self.request.user, course):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You must be enrolled to post in this course discussion.")
        serializer.save(course=course, author=self.request.user)

    def update(self, request, *args, **kwargs):
        post = self.get_object()
        user = request.user
        if post.author != user and user.role != "admin":
            return Response({"detail": "You can only edit your own posts."}, status=status.HTTP_403_FORBIDDEN)
        if post.is_closed and user.role != "admin":
            return Response({"detail": "This discussion is closed."}, status=status.HTTP_403_FORBIDDEN)
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    @extend_schema(
        summary="Toggle pin on a discussion post",
        description=(
            "Toggles the `is_pinned` flag on a post. Pinned posts appear at the top of the list.\n\n"
            + _ADMIN_ONLY_NOTE
        ),
        request=None,
        responses={
            200: OpenApiResponse(description='`{"is_pinned": true|false}`'),
            403: OpenApiResponse(description="Admin only."),
            404: OpenApiResponse(description="Post not found."),
        },
        tags=["Discussions"],
    )
    @action(detail=True, methods=["post"], url_path="pin")
    def pin(self, request, **kwargs):
        post = self.get_object()
        post.is_pinned = not post.is_pinned
        post.save(update_fields=["is_pinned"])
        return Response({"is_pinned": post.is_pinned})

    @extend_schema(
        summary="Toggle close on a discussion post",
        description=(
            "Toggles the `is_closed` flag. When closed, no new replies can be added (admins are exempt).\n\n"
            + _ADMIN_ONLY_NOTE
        ),
        request=None,
        responses={
            200: OpenApiResponse(description='`{"is_closed": true|false}`'),
            403: OpenApiResponse(description="Admin only."),
            404: OpenApiResponse(description="Post not found."),
        },
        tags=["Discussions"],
    )
    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, **kwargs):
        post = self.get_object()
        post.is_closed = not post.is_closed
        post.save(update_fields=["is_closed"])
        return Response({"is_closed": post.is_closed})


_REPLY_ACCESS_NOTE = (
    "**Access:** Enrolled students, the course teacher, active membership holders, and admins."
)
_REPLY_OWN_OR_ADMIN = "**Permissions:** Reply author, or admin."


@extend_schema_view(
    list=extend_schema(
        summary="List replies for a discussion post",
        description=(
            "Returns top-level replies only. Each reply includes nested `children` (one level deep).\n\n"
            + _REPLY_ACCESS_NOTE
        ),
        responses={
            200: ReplySerializer(many=True),
            403: OpenApiResponse(description="Not enrolled / not authenticated."),
        },
        tags=["Discussions"],
    ),
    retrieve=extend_schema(
        summary="Retrieve a single reply",
        description=(
            "Returns a single reply including its nested `children`.\n\n"
            + _REPLY_ACCESS_NOTE
        ),
        responses={
            200: ReplySerializer,
            403: OpenApiResponse(description="Not enrolled / not authenticated."),
            404: OpenApiResponse(description="Reply not found."),
        },
        tags=["Discussions"],
    ),
    create=extend_schema(
        summary="Add a reply to a discussion post",
        description=(
            "Creates a top-level reply or a threaded child reply.\n\n"
            "- Supply `parent` (reply ID) to create a child reply (one level deep only).\n"
            "- Omit `parent` for a top-level reply.\n"
            "- `post` and `author` are set automatically.\n\n"
            + _REPLY_ACCESS_NOTE + "\n\n"
            "Returns 403 if the discussion is closed (admins are exempt)."
        ),
        request=ReplySerializer,
        responses={
            201: ReplySerializer,
            403: OpenApiResponse(description="Not enrolled, or discussion is closed."),
        },
        tags=["Discussions"],
    ),
    partial_update=extend_schema(
        summary="Edit a reply",
        description=(
            "Partially updates a reply's `body` (PATCH).\n\n"
            + _REPLY_OWN_OR_ADMIN
        ),
        request=ReplySerializer,
        responses={
            200: ReplySerializer,
            403: OpenApiResponse(description="Not the author."),
            404: OpenApiResponse(description="Reply not found."),
        },
        tags=["Discussions"],
    ),
    update=extend_schema(exclude=True),
    destroy=extend_schema(
        summary="Delete a reply",
        description=(
            "Permanently deletes a reply and its children.\n\n"
            + _REPLY_OWN_OR_ADMIN
        ),
        responses={
            204: OpenApiResponse(description="Deleted successfully."),
            403: OpenApiResponse(description="Not the author."),
            404: OpenApiResponse(description="Reply not found."),
        },
        tags=["Discussions"],
    ),
)
class ReplyViewSet(viewsets.ModelViewSet):
    """
    GET    /courses/{slug}/discussions/{post_pk}/replies/      — list replies
    POST   /courses/{slug}/discussions/{post_pk}/replies/      — create reply
    PATCH  /courses/{slug}/discussions/{post_pk}/replies/{id}/ — edit own reply
    DELETE /courses/{slug}/discussions/{post_pk}/replies/{id}/ — author or admin
    """
    serializer_class = ReplySerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        base = Reply.objects.filter(post_id=self.kwargs["post_pk"])
        if self.action == "list":
            # List returns top-level only; children are nested inside each reply
            return base.filter(parent__isnull=True).select_related("author").prefetch_related("children__author")
        return base.select_related("author")

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def _get_post(self):
        return get_object_or_404(Post, pk=self.kwargs["post_pk"])

    def perform_create(self, serializer):
        post = self._get_post()
        course = post.course
        if not _can_access_course(self.request.user, course):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You must be enrolled to reply.")
        if post.is_closed and self.request.user.role != "admin":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("This discussion is closed.")
        serializer.save(post=post, author=self.request.user)

    def update(self, request, *args, **kwargs):
        reply = self.get_object()
        if reply.author != request.user and request.user.role != "admin":
            return Response({"detail": "You can only edit your own replies."}, status=status.HTTP_403_FORBIDDEN)
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        reply = self.get_object()
        if reply.author != request.user and request.user.role != "admin":
            return Response({"detail": "You can only delete your own replies."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)
