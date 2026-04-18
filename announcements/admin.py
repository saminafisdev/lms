from django.contrib import admin

from .models import CourseAnnouncement, SiteAnnouncement


@admin.register(CourseAnnouncement)
class CourseAnnouncementAdmin(admin.ModelAdmin):
    list_display = ["title", "course", "created_by", "created_at"]
    list_filter = ["course"]
    search_fields = ["title", "body"]
    readonly_fields = ["created_at"]


@admin.register(SiteAnnouncement)
class SiteAnnouncementAdmin(admin.ModelAdmin):
    list_display = ["main_title", "is_active", "created_at"]
    list_filter = ["is_active"]
    readonly_fields = ["created_at"]
