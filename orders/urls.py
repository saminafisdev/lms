from orders.views import BookSalesViewSet
from orders.views import StripeWebhookView
from django.urls import path
from .views import CartViewSet, OrderViewSet

cart_list = CartViewSet.as_view({"get": "list"})
cart_add = CartViewSet.as_view({"post": "create"})
cart_item = CartViewSet.as_view({"patch": "partial_update", "delete": "destroy"})
cart_clear = CartViewSet.as_view({"delete": "clear"})

order_list = OrderViewSet.as_view({"get": "list"})
order_detail = OrderViewSet.as_view({"get": "retrieve"})
order_direct = OrderViewSet.as_view({"post": "direct_purchase"})
order_checkout = OrderViewSet.as_view({"post": "checkout"})
order_webhook = OrderViewSet.as_view({"post": "webhook"})

book_sales_list = BookSalesViewSet.as_view({"get": "list"})
book_sales_detail = BookSalesViewSet.as_view({"get": "retrieve"})
book_sales_summary = BookSalesViewSet.as_view({"get": "summary"})

urlpatterns = [
    # Cart
    path("cart/", cart_list, name="cart"),
    path("cart/items/", cart_add, name="cart-add"),
    path("cart/items/<int:pk>/", cart_item, name="cart-item"),
    path("cart/clear/", cart_clear, name="cart-clear"),
    # Orders
    path("orders/", order_list, name="order-list"),
    path("orders/<int:pk>/", order_detail, name="order-detail"),
    path("orders/direct/", order_direct, name="order-direct"),
    path("orders/checkout/", order_checkout, name="order-checkout"),
    # Book sales — admin only
    path("orders/book-sales/", book_sales_list, name="book-sales-list"),
    path("orders/book-sales/summary/", book_sales_summary, name="book-sales-summary"),
    path("orders/book-sales/<int:pk>/", book_sales_detail, name="book-sales-detail"),
    # Stripe webhook
    path("orders/webhook/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
