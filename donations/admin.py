from django.contrib import admin
from .models import Donation


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "amount", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("first_name", "last_name", "email")
    readonly_fields = ("stripe_reference", "created_at", "updated_at")
