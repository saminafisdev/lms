from rest_framework import viewsets, permissions, filters, status
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Book, BookCategory, BookGalleryImage
from .serializers import (
    BookCategorySerializer, AdminBookSerializer, PublicBookSerializer, BookGalleryImageSerializer
)
from doors.permissions import IsAdminRole


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
        if getattr(self, 'swagger_fake_view', False):
            return AdminBookSerializer

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

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Related books: same category, excluding self, up to 4
        related_qs = self.get_queryset().filter(
            category=instance.category
        ).exclude(pk=instance.pk).select_related("category")[:4]
        data["related_books"] = self.get_serializer(related_qs, many=True).data

        return Response(data)


class BookGalleryImageViewSet(viewsets.ModelViewSet):
    """
    Manage gallery images for a specific book.
    Admin only — nested under /books/{book_slug}/gallery/
    Supports bulk upload via POST with multiple files under the 'images' key.
    """
    serializer_class = BookGalleryImageSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        return BookGalleryImage.objects.filter(book__slug=self.kwargs['book_slug'])

    def perform_create(self, serializer):
        book = Book.objects.get(slug=self.kwargs['book_slug'])
        serializer.save(book=book)

    def create(self, request, *args, **kwargs):
        try:
            book = Book.objects.get(slug=self.kwargs['book_slug'])
        except Book.DoesNotExist:
            return Response(
                {"error": "Book not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        images = request.FILES.getlist('images')

        if not images:
            return Response(
                {"error": "No images provided. Send files under the 'images' key."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Continue ordering from where existing images left off
        last_order = BookGalleryImage.objects.filter(book=book).count()

        created = []
        for index, image in enumerate(images):
            instance = BookGalleryImage.objects.create(
                book=book,
                image=image,
                order=last_order + index
            )
            created.append(
                BookGalleryImageSerializer(instance, context={'request': request}).data
            )

        return Response(created, status=status.HTTP_201_CREATED)