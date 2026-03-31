from django.contrib import admin
from .models import Blog, BlogCategory


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "category", "status", "published_at", "created_at"]
    list_filter = ["status", "category"]
    search_fields = ["title", "content", "author__user__email"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["reading_time", "view_count", "published_at", "created_at", "updated_at"]
    fieldsets = (
        (None, {
            "fields": ("title", "slug", "author", "category", "cover_image", "excerpt", "content", "tags")
        }),
        ("Status", {
            "fields": ("status", "rejection_reason")
        }),
        ("Metadata", {
            "fields": ("reading_time", "view_count", "published_at", "created_at", "updated_at")
        }),
    )