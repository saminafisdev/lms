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
        "has_digital", "digital_price", "lulu_pod_package_id", "is_visible"
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
            "fields": ("isbn", "language", "publisher", "published_date", "page_count")
        }),
        ("Media", {
            "fields": ("sample_file", "video_url")
        }),
        ("Physical Version", {
            "fields": ("has_physical", "physical_price", "stock_count")
        }),
        ("Lulu Print-on-Demand", {
            "fields": ("lulu_pod_package_id", "lulu_cover_pdf"),
            "description": (
                "Set these to enable automatic printing and international shipping via Lulu. "
                "The interior PDF is taken from the uploaded digital_file. "
                "pod_package_id encodes paper size, binding, and color — "
                "e.g. 0600X0900BWSTDSS060UW444MXX = 6x9 B&W perfect-bound paperback. "
                "lulu_cover_pdf must be a print-ready PDF (front + spine + back with bleed) — "
                "NOT a JPEG or WebP. Generate it using Lulu's cover generator."
            ),
        }),
        ("Digital Version", {
            "fields": ("has_digital", "digital_price", "digital_file")
        }),
        ("Settings", {
            "fields": ("is_visible",)
        }),
    )


@admin.register(BookGalleryImage)
class BookGalleryImageAdmin(admin.ModelAdmin):
    list_display = ("book", "order")
    list_filter = ("book",)
