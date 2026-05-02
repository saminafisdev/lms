from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, StudentProfile, TeacherProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "role", "is_active", "is_staff"]
    list_filter = ["role", "is_active", "is_staff"]
    search_fields = ["email", "first_name", "last_name"]

    fieldsets = (
        ("Account", {"fields": ("first_name", "last_name", "email", "password")}),
        ("Role & Status", {"fields": ("role", "is_active", "is_staff", "is_superuser")}),
        ("Permissions", {"classes": ("collapse",), "fields": ("groups", "user_permissions")}),
        ("Important dates", {"classes": ("collapse",), "fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("first_name", "last_name", "email", "role", "password1", "password2"),
        }),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "is_subscribed_to_newsletter"]


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "professional_title", "location"]
