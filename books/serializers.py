from config.fields import RichTextField
from rest_framework import serializers
from .models import Book, BookCategory, BookGalleryImage

class BookCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BookCategory
        fields = ["id", "name", "slug"]
        read_only_fields = ["id", "slug"]

class BookGalleryImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookGalleryImage
        fields = ["id", "image", "order"]

class AdminBookSerializer(serializers.ModelSerializer):
    """
    Full serializer for admin management.
    """
    category_name = serializers.ReadOnlyField(source="category.name")
    gallery_images = BookGalleryImageSerializer(many=True, read_only=True)
    description = RichTextField()

    class Meta:
        model = Book
        fields = [
            "id", "category", "category_name", "title", "slug", "author", "description", 
            "cover_image", "isbn", "language", "publisher", "published_date", 
            "number_of_pages", "sample_file", "video_url", "has_physical", 
            "physical_price", "stock_count", "has_digital", "digital_price", 
            "tags", "is_visible", "created_at", "updated_at", "gallery_images"
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at", "gallery_images"]

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
            "id", "category", "title", "slug", "author", "description", 
            "cover_image", "isbn", "language", "publisher", "published_date", 
            "number_of_pages", "sample_file", "video_url", "has_physical", 
            "physical_price", "stock_count", "has_digital", "digital_price", 
            "tags", "created_at", "updated_at", "gallery_images"
        ]
        read_only_fields = fields
