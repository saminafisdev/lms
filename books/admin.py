from django.contrib import admin
from .models import Book, BookCategory, BookGalleryImage

class BookGalleryImageInline(admin.TabularInline):
    model = BookGalleryImage
    extra = 1

@admin.register(BookCategory)
class BookCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = (
        "title", "author", "has_physical", "physical_price", 
        "has_digital", "digital_price", "is_visible"
    )
    list_filter = ("is_visible", "has_physical", "has_digital", "category")
    search_fields = ("title", "author", "isbn", "description")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [BookGalleryImageInline]
    fieldsets = (
        (None, {
            "fields": ("title", "slug", "author", "category", "description", "cover_image")
        }),
        ("Details", {
            "fields": ("isbn", "language", "publisher", "published_date", "number_of_pages")
        }),
        ("Media", {
            "fields": ("sample_file", "video_url")
        }),
        ("Physical Version", {
            "fields": ("has_physical", "physical_price", "stock_count")
        }),
        ("Digital Version", {
            "fields": ("has_digital", "digital_price")
        }),
        ("Settings", {
            "fields": ("is_visible",)
        }),
    )

@admin.register(BookGalleryImage)
class BookGalleryImageAdmin(admin.ModelAdmin):
    list_display = ("book", "order")
    list_filter = ("book",)
