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
    # Stripe webhook
    path("orders/webhook/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
