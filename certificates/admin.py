from django.contrib import admin
from .models import Certificate, CertificateTemplate


@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "course", "created_by", "created_at"]
    search_fields = ["name", "course__title"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ["certificate_id", "student", "course", "issued_at", "issued_by"]
    list_filter = ["course"]
    search_fields = ["student__email", "course__title", "certificate_id"]
    readonly_fields = ["certificate_id", "issued_at"]
