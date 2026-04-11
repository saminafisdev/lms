from django.shortcuts import render
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from config.permissions import IsAdminRole

from .models import Review
from .serializers import ReviewSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    """
    Handles reviews for courses, books, and consultations.

    Students POST to:
      /reviews/courses/{course_id}/
      /reviews/books/{book_id}/
      /reviews/consultations/{consultation_id}/

    Anyone can GET the list of reviews per resource.
    Only the owner or admin can update/delete a review.
    """

    serializer_class = ReviewSerializer
    http_method_names = ["get", "post", "patch", "delete"]

    REVIEW_TYPE_MAP = {
        "course_pk": "course",
        "book_pk": "book",
        "consultation_pk": "consultation",
    }

    def _get_review_type(self):
        for kwarg_key, review_type in self.REVIEW_TYPE_MAP.items():
            if kwarg_key in self.kwargs:
                return review_type
        return None

    def get_queryset(self):
        qs = Review.objects.select_related("user", "course", "book", "consultation")
        review_type = self._get_review_type()
        if review_type == "course":
            return qs.filter(course_id=self.kwargs["course_pk"])
        if review_type == "book":
            return qs.filter(book_id=self.kwargs["book_pk"])
        if review_type == "consultation":
            return qs.filter(consultation_id=self.kwargs["consultation_pk"])
        # Admin-only flat list
        return qs.all()

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        if self.action in ("partial_update", "destroy"):
            return [permissions.IsAuthenticated()]
        if self.action == "list" and not any(k in self.kwargs for k in self.REVIEW_TYPE_MAP):
            return [IsAdminRole()]
        return [permissions.AllowAny()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["review_type"] = self._get_review_type()
        return context

    def create(self, request, *args, **kwargs):
        review_type = self._get_review_type()
        if not review_type:
            return Response(
                {"error": "Cannot create a review at this endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Inject the FK from the URL into the data
        data = request.data.copy()
        pk_key = f"{review_type}_pk"
        data[review_type] = self.kwargs[pk_key]

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        review = self.get_object()
        if review.user != request.user and not (
            request.user.is_staff or getattr(request.user, "role", None) == "admin"
        ):
            return Response(status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(review, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        review = self.get_object()
        if review.user != request.user and not (
            request.user.is_staff or getattr(request.user, "role", None) == "admin"
        ):
            return Response(status=status.HTTP_403_FORBIDDEN)
        review.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

