from orders.views import BookSalesViewSet, LuluWebhookView, SalesViewSet
from orders.views import StripeWebhookView
from django.urls import path
from .views import CartViewSet, CouponViewSet, OrderViewSet

cart_list = CartViewSet.as_view({"get": "list"})
cart_add = CartViewSet.as_view({"post": "create"})
cart_item = CartViewSet.as_view({"patch": "partial_update", "delete": "destroy"})
cart_clear = CartViewSet.as_view({"delete": "clear"})
cart_estimate_shipping = CartViewSet.as_view({"post": "estimate_shipping"})

cart_validate_coupon = CartViewSet.as_view({"post": "validate_coupon"})

coupon_list = CouponViewSet.as_view({"get": "list", "post": "create"})
coupon_detail = CouponViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})


order_list = OrderViewSet.as_view({"get": "list"})
order_detail = OrderViewSet.as_view({"get": "retrieve"})
order_direct = OrderViewSet.as_view({"post": "direct_purchase"})
order_checkout = OrderViewSet.as_view({"post": "checkout"})
order_webhook = OrderViewSet.as_view({"post": "webhook"})

book_sales_list = BookSalesViewSet.as_view({"get": "list"})
book_sales_detail = BookSalesViewSet.as_view({"get": "retrieve"})
book_sales_summary = BookSalesViewSet.as_view({"get": "summary"})

sales_list = SalesViewSet.as_view({"get": "list"})
sales_summary = SalesViewSet.as_view({"get": "summary"})

urlpatterns = [
    # Cart
    path("cart/", cart_list, name="cart"),
    path("cart/items/", cart_add, name="cart-add"),
    path("cart/items/<int:pk>/", cart_item, name="cart-item"),
    path("cart/clear/", cart_clear, name="cart-clear"),
    path("cart/estimate-shipping/", cart_estimate_shipping, name="cart-estimate-shipping"),
    path("cart/validate-coupon/", cart_validate_coupon, name="cart-validate-coupon"),
    # Orders
    path("orders/", order_list, name="order-list"),
    path("orders/<int:pk>/", order_detail, name="order-detail"),
    path("orders/direct/", order_direct, name="order-direct"),
    path("orders/checkout/", order_checkout, name="order-checkout"),
    # Book sales — admin only
    path("orders/book-sales/", book_sales_list, name="book-sales-list"),
    path("orders/book-sales/summary/", book_sales_summary, name="book-sales-summary"),
    path("orders/book-sales/<int:pk>/", book_sales_detail, name="book-sales-detail"),
    # Unified sales — admin only
    path("orders/sales/", sales_list, name="sales-list"),
    path("orders/sales/summary/", sales_summary, name="sales-summary"),
    # Stripe webhook
    path("orders/webhook/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
    # Lulu webhook
    path("orders/webhook/lulu/", LuluWebhookView.as_view(), name="lulu-webhook"),
    # Coupons — admin CRUD
    path("coupons/", coupon_list, name="coupon-list"),
    path("coupons/<int:pk>/", coupon_detail, name="coupon-detail"),
]
