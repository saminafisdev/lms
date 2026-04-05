from django.contrib import admin
from .models import Video, VideoCategory


@admin.register(VideoCategory)
class VideoCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "category", "status", "published_at", "created_at"]
    list_filter = ["status", "category"]
    search_fields = ["title", "content", "author__user__email"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["view_count", "published_at", "created_at", "updated_at"]
    fieldsets = (
        (None, {
            "fields": ("title", "slug", "author", "category", "video_url", "cover_image", "excerpt", "content", "tags")
        }),
        ("Status", {
            "fields": ("status", "rejection_reason")
        }),
        ("Metadata", {
            "fields": ("view_count", "published_at", "created_at", "updated_at")
        }),
    )
