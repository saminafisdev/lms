from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers as drf_serializers
from .models import Book, BookCategory, BookGalleryImage
from .serializers import (
    BookCategorySerializer, AdminBookSerializer, PublicBookSerializer,
    BookGalleryImageSerializer, PurchasedBookSerializer,
)
from doors.permissions import IsAdminRole
from orders.utils import has_access


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


_GALLERY_IMAGES_FIELD = inline_serializer(
    name="BookWithGalleryInput",
    fields={"gallery_images": drf_serializers.ListField(
        child=drf_serializers.ImageField(),
        required=False,
        help_text="Upload one or more gallery images in a single request (multipart/form-data).",
    )},
)


@extend_schema_view(
    create=extend_schema(
        request={
            "multipart/form-data": inline_serializer(
                name="BookCreateInput",
                fields={
                    **{k: v for k, v in AdminBookSerializer().fields.items()
                       if k not in ("gallery_images",)},
                    "gallery_images": drf_serializers.ListField(
                        child=drf_serializers.ImageField(),
                        required=False,
                        help_text="Upload one or more gallery images (repeat field for multiple files).",
                    ),
                },
            )
        },
        summary="Create a book with optional gallery images",
    ),
    update=extend_schema(
        request={
            "multipart/form-data": inline_serializer(
                name="BookUpdateInput",
                fields={
                    **{k: v for k, v in AdminBookSerializer().fields.items()
                       if k not in ("gallery_images",)},
                    "gallery_images": drf_serializers.ListField(
                        child=drf_serializers.ImageField(),
                        required=False,
                        help_text="Append new gallery images (repeat field for multiple files).",
                    ),
                },
            )
        },
        summary="Update a book and optionally append gallery images",
    ),
    partial_update=extend_schema(
        request={
            "multipart/form-data": inline_serializer(
                name="BookPartialUpdateInput",
                fields={
                    **{k: v for k, v in AdminBookSerializer().fields.items()
                       if k not in ("gallery_images",)},
                    "gallery_images": drf_serializers.ListField(
                        child=drf_serializers.ImageField(),
                        required=False,
                        help_text="Append new gallery images (repeat field for multiple files).",
                    ),
                },
            )
        },
        summary="Partially update a book and optionally append gallery images",
    ),
)
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
        elif self.action in ["read", "my_library"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [IsAdminRole]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == "admin":
            return Book.objects.all()
        return Book.objects.filter(is_visible=True)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        book = serializer.save()

        # Accept multiple gallery images in the same create request
        images = request.FILES.getlist("gallery_images")
        for index, image in enumerate(images):
            BookGalleryImage.objects.create(book=book, image=image, order=index)

        headers = self.get_success_headers(serializer.data)
        # Re-serialize to include the newly created gallery images
        return Response(
            self.get_serializer(book).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        book = serializer.save()

        # Append any new gallery images sent with update
        images = request.FILES.getlist("gallery_images")
        if images:
            last_order = BookGalleryImage.objects.filter(book=book).count()
            for index, image in enumerate(images):
                BookGalleryImage.objects.create(book=book, image=image, order=last_order + index)

        return Response(self.get_serializer(book).data)


        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Related books: same category, excluding self, up to 4
        related_qs = self.get_queryset().filter(
            category=instance.category
        ).exclude(pk=instance.pk).select_related("category")[:4]
        data["related_books"] = self.get_serializer(related_qs, many=True).data

        return Response(data)

    @action(detail=False, methods=["get"], url_path="my-library",
            permission_classes=[permissions.IsAuthenticated])
    def my_library(self, request):
        """
        GET /books/my-library/
        Returns all digital books the authenticated user has purchased.
        """
        from orders.models import OrderItem
        book_ids = OrderItem.objects.filter(
            order__user=request.user,
            order__status="completed",
            item_type="digital_book",
        ).values_list("book_id", flat=True).distinct()

        books = Book.objects.filter(id__in=book_ids)
        serializer = PurchasedBookSerializer(books, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="read",
            permission_classes=[permissions.IsAuthenticated])
    def read(self, request, slug=None):
        """
        GET /books/{slug}/read/
        Returns a short-lived signed URL for reading the digital book in-browser.
        The URL expires in 2 hours. Returns 403 if not purchased.
        """
        from config.bunny_storage import generate_bunny_signed_url

        book = self.get_object()

        if not book.has_digital:
            return Response(
                {"error": "This book does not have a digital edition."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not has_access(request.user, book, format="digital"):
            return Response(
                {"error": "You have not purchased the digital edition of this book."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not book.digital_file:
            return Response(
                {"error": "The digital file is not available yet. Please contact support."},
                status=status.HTTP_404_NOT_FOUND,
            )

        expiry_seconds = 7200  # 2 hours
        signed_url = generate_bunny_signed_url(book.digital_file.name, expiry_seconds)

        return Response({
            "url": signed_url,
            "expires_in": expiry_seconds,
        })

    @extend_schema(
        responses={200: inline_serializer("LuluSpecsSerializer", fields={
            "results": drf_serializers.ListField(child=drf_serializers.DictField()),
        })},
        summary="List available Lulu pod_package_id options",
        description="Admin only. Returns all print specs from Lulu (paper size, binding, color) to help pick a pod_package_id for a book.",
        tags=["Books"],
    )
    @action(detail=False, methods=["get"], url_path="lulu-packages",
            permission_classes=[IsAdminRole])
    def lulu_packages(self, request):
        """
        GET /books/lulu-packages/
        Returns common Lulu pod_package_id options with human-readable descriptions.
        Admin only.
        """
        from orders.lulu import get_print_specs
        return Response(get_print_specs())

    @extend_schema(
        request=inline_serializer("LuluValidateRequestSerializer", fields={
            "pod_package_id": drf_serializers.CharField(required=False, help_text="Optional — include for extended normalization validation"),
        }),
        responses={202: inline_serializer("LuluValidateResponseSerializer", fields={
            "validation_id": drf_serializers.IntegerField(),
            "status": drf_serializers.CharField(),
            "message": drf_serializers.CharField(),
        })},
        summary="Submit interior PDF for Lulu validation",
        description=(
            "Admin only. Submits the book's digital_file PDF to Lulu for async validation. "
            "Returns a validation_id — poll GET /books/{slug}/lulu-validate-result/?validation_id=X for the result. "
            "If pod_package_id is provided, Lulu also checks if the PDF matches that format."
        ),
        tags=["Books"],
    )
    @action(detail=True, methods=["post"], url_path="lulu-validate",
            permission_classes=[IsAdminRole])
    def lulu_validate(self, request, slug=None):
        """
        POST /books/{slug}/lulu-validate/
        Submit the book's interior PDF to Lulu for validation.
        Admin only.
        """
        book = self.get_object()
        if not book.digital_file:
            return Response(
                {"error": "This book has no digital_file to validate."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from orders.lulu import submit_interior_validation
            pod_package_id = request.data.get("pod_package_id") or book.lulu_pod_package_id or None
            result = submit_interior_validation(
                source_url=book.digital_file.url,
                pod_package_id=pod_package_id,
            )
            return Response(
                {
                    "validation_id": result["id"],
                    "status": result.get("status"),
                    "message": "Validation submitted. Poll lulu-validate-result/ with this validation_id for the result.",
                },
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as e:
            msg = str(e)
            if "405" in msg:
                msg = (
                    "Lulu interior validation returned 405 — your Lulu API account may not have "
                    "validation permissions enabled. Contact Lulu support to request access, "
                    "or manually set the pod_package_id from the /books/lulu-packages/ reference list."
                )
            return Response({"error": msg}, status=status.HTTP_502_BAD_GATEWAY)

    @extend_schema(
        parameters=[
            inline_serializer("LuluValidateResultParams", fields={
                "validation_id": drf_serializers.IntegerField(),
            })
        ],
        responses={200: inline_serializer("LuluValidateResultSerializer", fields={
            "status": drf_serializers.CharField(),
            "page_count": drf_serializers.CharField(required=False),
            "errors": drf_serializers.ListField(child=drf_serializers.CharField(), required=False),
            "valid_pod_package_ids": drf_serializers.ListField(child=drf_serializers.CharField(), required=False),
        })},
        summary="Poll Lulu interior validation result",
        description=(
            "Admin only. Poll the result of a previously submitted validation. "
            "Status will be VALIDATING/VALIDATED/NORMALIZED/ERROR. "
            "valid_pod_package_ids lists all compatible pod_package_ids for this PDF."
        ),
        tags=["Books"],
    )
    @action(detail=False, methods=["get"], url_path="lulu-validate-result",
            permission_classes=[IsAdminRole])
    def lulu_validate_result(self, request):
        """
        GET /books/lulu-validate-result/?validation_id=123
        Poll the result of a Lulu interior validation.
        Admin only.
        """
        validation_id = request.query_params.get("validation_id")
        if not validation_id:
            return Response(
                {"error": "validation_id query param is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from orders.lulu import get_interior_validation
            result = get_interior_validation(int(validation_id))
            return Response({
                "status": result.get("status"),
                "page_count": result.get("page_count"),
                "errors": result.get("errors", []),
                "valid_pod_package_ids": result.get("valid_pod_package_ids", []),
            })
        except Exception as e:
            return Response(
                {"error": f"Failed to fetch validation result: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


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