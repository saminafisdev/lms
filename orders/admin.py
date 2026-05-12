from django.contrib import admin
from .models import Cart, CartItem, Coupon, Order, OrderItem, ShippingAddress


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ["item_type", "course", "bundle", "book", "quantity", "added_at"]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "updated_at"]
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["item_type", "course", "bundle", "book", "quantity", "unit_price", "total_price", "lulu_print_job_id"]


class ShippingAddressInline(admin.StackedInline):
    model = ShippingAddress
    extra = 0
    readonly_fields = ["full_name", "phone", "address_line", "city", "country", "postal_code"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "order_type", "status", "fulfillment_status", "total_amount", "created_at"]
    list_filter = ["status", "order_type", "fulfillment_status"]
    search_fields = ["user__email", "payment_reference"]
    readonly_fields = ["total_amount", "payment_reference", "created_at", "updated_at"]
    inlines = [OrderItemInline, ShippingAddressInline]


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "discount_type", "discount_value", "is_active", "expires_at", "created_at"]
    list_filter = ["discount_type", "is_active"]
    search_fields = ["code"]
