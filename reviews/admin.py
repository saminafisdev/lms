from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["user", "review_type", "rating", "course", "book", "consultation", "created_at"]
    list_filter = ["review_type", "rating"]
    search_fields = ["user__email", "comment"]
    readonly_fields = ["user", "review_type", "course", "book", "consultation", "created_at"]

