from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Book, BookCategory, BookGalleryImage
from .serializers import (
    BookCategorySerializer, AdminBookSerializer, PublicBookSerializer
)
from doors.permissions import IsAdminRole # Reuse logic

class BookCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing book categories.
    - Public: List and retrieve.
    - Admin: Full CRUD.
    """
    queryset = BookCategory.objects.all()
    serializer_class = BookCategorySerializer
    lookup_field = "slug"
    pagination_class = None

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [IsAdminRole]
        return [permission() for permission in permission_classes]

class BookViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing books.
    - Public: List and retrieve visible books.
    - Admin: Full CRUD on all books.
    """
    queryset = Book.objects.all()
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category__slug", "has_physical", "has_digital"]
    search_fields = ["title", "author", "description", "isbn"]
    ordering_fields = ["published_date", "created_at", "title"]

    def get_serializer_class(self):
        user = self.request.user
        if user.is_authenticated and user.role == "admin":
            return AdminBookSerializer
        return PublicBookSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [IsAdminRole]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == "admin":
            return Book.objects.all()
        return Book.objects.filter(is_visible=True)
