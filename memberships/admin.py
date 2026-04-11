from django.contrib import admin
from .models import MembershipPlan, UserMembership


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    fields = ("name", "description", "price", "duration_days", "is_active", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not MembershipPlan.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserMembership)
class UserMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "start_date", "end_date", "updated_at")
    list_filter = ("status",)
    search_fields = ("user__email",)
    readonly_fields = ("payment_reference", "created_at", "updated_at")
