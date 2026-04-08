from django.contrib import admin
from .models import EmailTemplateConfig


@admin.register(EmailTemplateConfig)
class EmailTemplateConfigAdmin(admin.ModelAdmin):
    list_display = [
        "purpose",
        "sendgrid_template_id",
        "is_active",
        "updated_at",
        "updated_by",
    ]
    list_filter = ["is_active", "purpose"]
    readonly_fields = ["updated_at", "updated_by"]
