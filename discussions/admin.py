from django.contrib import admin
from .models import Post, Reply


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["title", "course", "author", "is_pinned", "is_closed", "created_at"]
    list_filter = ["is_pinned", "is_closed", "course"]
    search_fields = ["title", "body", "author__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ["__str__", "post", "author", "parent", "created_at"]
    search_fields = ["body", "author__email"]
    readonly_fields = ["created_at", "updated_at"]
