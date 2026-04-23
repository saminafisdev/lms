from config.fields import RichTextField
from rest_framework import serializers
from .models import Book, BookCategory, BookGalleryImage
from config.mixins import SlugMixin


class BookCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BookCategory
        fields = ["id", "name", "slug"]
        read_only_fields = ["id", "slug"]


class BookGalleryImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookGalleryImage
        fields = ["id", "image", "order"]


class AdminBookSerializer(SlugMixin, serializers.ModelSerializer):
    slug_source_field = "title"
    category_name = serializers.ReadOnlyField(source="category.name")
    gallery_images = BookGalleryImageSerializer(many=True, read_only=True)
    description = RichTextField()

    class Meta:
        model = Book
        fields = [
            "id",
            "category",
            "category_name",
            "title",
            "slug",
            "author",
            "author_designation",
            "description",
            "cover_image",
            "isbn",
            "language",
            "publisher",
            "published_date",
            "number_of_pages",
            "sample_file",
            "digital_file",
            "video_url",
            "has_physical",
            "physical_price",
            "stock_count",
            "lulu_pod_package_id",
            "has_digital",
            "digital_price",
            "tags",
            "is_visible",
            "created_at",
            "updated_at",
            "gallery_images",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "gallery_images"]


class PublicBookSerializer(serializers.ModelSerializer):
    """
    Public serializer for all users, excludes internal management fields (is_visible).
    Includes nested category and gallery.
    """

    category = BookCategorySerializer(read_only=True)
    gallery_images = BookGalleryImageSerializer(many=True, read_only=True)
    description = RichTextField()

    class Meta:
        model = Book
        fields = [
            "id",
            "category",
            "title",
            "slug",
            "author",
            "description",
            "cover_image",
            "isbn",
            "language",
            "publisher",
            "published_date",
            "number_of_pages",
            "sample_file",
            "video_url",
            "has_physical",
            "physical_price",
            "stock_count",
            "has_digital",
            "digital_price",
            "tags",
            "created_at",
            "updated_at",
            "gallery_images",
        ]
        read_only_fields = fields


class PurchasedBookSerializer(serializers.ModelSerializer):
    """Minimal serializer for a user's digital library — never exposes digital_file URL."""
    category = BookCategorySerializer(read_only=True)

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "slug",
            "author",
            "cover_image",
            "category",
            "number_of_pages",
            "language",
            "has_digital",
            "digital_price",
        ]
