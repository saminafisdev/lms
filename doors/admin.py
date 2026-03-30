from django.contrib import admin
from .models import Door

@admin.register(Door)
class DoorAdmin(admin.ModelAdmin):
    list_display = ("title", "is_visible", "created_at", "updated_at")
    list_filter = ("is_visible", "created_at")
    search_fields = ("title", "content")
    ordering = ("-created_at",)
