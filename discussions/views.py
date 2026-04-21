import logging

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
    return get_object_or_404(Course, slug=kwargs["course_slug"])


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


class PostViewSet(viewsets.ModelViewSet):
    """
    GET    /courses/{slug}/discussions/           — list posts
    POST   /courses/{slug}/discussions/           — create post
    GET    /courses/{slug}/discussions/{id}/      — retrieve post + replies
    PATCH  /courses/{slug}/discussions/{id}/      — edit own post (or admin)
    DELETE /courses/{slug}/discussions/{id}/      — admin only
    POST   /courses/{slug}/discussions/{id}/pin/  — admin only
    POST   /courses/{slug}/discussions/{id}/close/ — admin only
    """

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

    @action(detail=True, methods=["post"], url_path="pin")
    def pin(self, request, **kwargs):
        post = self.get_object()
        post.is_pinned = not post.is_pinned
        post.save(update_fields=["is_pinned"])
        return Response({"is_pinned": post.is_pinned})

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, **kwargs):
        post = self.get_object()
        post.is_closed = not post.is_closed
        post.save(update_fields=["is_closed"])
        return Response({"is_closed": post.is_closed})


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
        return Reply.objects.filter(
            post_id=self.kwargs["post_pk"],
            parent__isnull=True,  # top-level only; children nested via serializer
        ).select_related("author").prefetch_related("children__author")

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
