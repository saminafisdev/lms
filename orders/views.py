import stripe as stripe_lib
from django.conf import settings
from django.db import models
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsAdminRole
from email_templates.sendgrid import send_email
from orders.models import ShippingAddress
from orders.serializers import BookSaleSerializer
from orders.stripe import construct_webhook_event, create_payment_intent

from .models import Cart, CartItem, Order, OrderItem
from .serializers import (
    CartCheckoutSerializer,
    CartItemSerializer,
    CartSerializer,
    DirectPurchaseSerializer,
    OrderSerializer,
)
from .utils import already_owns


class CartViewSet(viewsets.ViewSet):
    """Cart management — physical books only."""

    permission_classes = [permissions.IsAuthenticated]

    def get_or_create_cart(self, user):
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    @extend_schema(responses={200: CartSerializer})
    def list(self, request):
        """GET /cart/ — view cart."""
        cart = self.get_or_create_cart(request.user)
        serializer = CartSerializer(cart, context={"request": request})
        return Response(serializer.data)

    @extend_schema(request=CartItemSerializer, responses={201: CartItemSerializer})
    def create(self, request):
        """POST /cart/items/ — add item to cart."""
        cart = self.get_or_create_cart(request.user)
        serializer = CartItemSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        book = serializer.validated_data["book"]

        # Block if already owns physical copy
        if already_owns(request.user, book, format="physical"):
            return Response(
                {"error": "You already own the physical version of this book."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update quantity if already in cart, else create
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            book=book,
            defaults={"quantity": serializer.validated_data.get("quantity", 1)},
        )
        if not created:
            cart_item.quantity += serializer.validated_data.get("quantity", 1)
            cart_item.save()

        return Response(
            CartItemSerializer(cart_item, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={204: None})
    def destroy(self, request, pk=None):
        """DELETE /cart/items/{id}/ — remove item."""
        cart = self.get_or_create_cart(request.user)
        try:
            item = CartItem.objects.get(id=pk, cart=cart)
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CartItem.DoesNotExist:
            return Response(
                {"error": "Item not found in cart."}, status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(request=CartItemSerializer, responses={200: CartItemSerializer})
    def partial_update(self, request, pk=None):
        """PATCH /cart/items/{id}/ — update quantity."""
        cart = self.get_or_create_cart(request.user)
        try:
            item = CartItem.objects.get(id=pk, cart=cart)
        except CartItem.DoesNotExist:
            return Response(
                {"error": "Item not found in cart."}, status=status.HTTP_404_NOT_FOUND
            )

        quantity = request.data.get("quantity")
        if not quantity or int(quantity) < 1:
            return Response(
                {"error": "Quantity must be at least 1."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if int(quantity) > item.book.stock_count:
            return Response(
                {"error": f"Only {item.book.stock_count} copies available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item.quantity = int(quantity)
        item.save()
        return Response(CartItemSerializer(item, context={"request": request}).data)

    @extend_schema(responses={204: None})
    @action(detail=False, methods=["delete"], url_path="clear")
    def clear(self, request):
        """DELETE /cart/clear/ — empty cart."""
        cart = self.get_or_create_cart(request.user)
        cart.items.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrderViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OrderSerializer(many=True)})
    def list(self, request):
        """GET /orders/ — user's order history."""
        orders = Order.objects.filter(user=request.user)
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """GET /orders/{id}/"""
        try:
            order = Order.objects.get(id=pk, user=request.user)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(OrderSerializer(order).data)

    @extend_schema(request=DirectPurchaseSerializer, responses={201: OrderSerializer})
    @action(detail=False, methods=["post"], url_path="direct")
    def direct_purchase(self, request):
        """
        POST /orders/direct/
        Buy a course or digital book directly.
        """
        serializer = DirectPurchaseSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        item_type = serializer.validated_data["item_type"]
        obj = serializer.validated_data["object"]
        price = serializer.validated_data["price"]

        order = Order.objects.create(
            user=request.user, order_type="direct", status="pending", total_amount=price
        )

        course = obj if item_type == "course" else None
        book = obj if item_type == "digital_book" else None

        OrderItem.objects.create(
            order=order,
            item_type=item_type,
            course=course,
            book=book,
            unit_price=price,
            total_price=price,
        )

        # Create Stripe PaymentIntent
        intent = create_payment_intent(
            amount=price,
            metadata={
                "order_id": order.id,
                "user_id": request.user.id,
            },
        )

        # Save payment reference
        order.payment_reference = intent["id"]
        order.save(update_fields=["payment_reference"])

        return Response(
            {
                "order": OrderSerializer(order).data,
                "client_secret": intent["client_secret"],
                "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=CartCheckoutSerializer, responses={201: OrderSerializer})
    @action(detail=False, methods=["post"], url_path="checkout")
    def checkout(self, request):
        """
        POST /orders/checkout/
        Checkout physical books from cart.
        """
        serializer = CartCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = Cart.objects.filter(user=request.user).first()
        if not cart or not cart.items.exists():
            return Response(
                {"error": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate stock for all items before creating order
        for item in cart.items.all():
            if item.quantity > item.book.stock_count:
                return Response(
                    {
                        "error": f"'{item.book.title}' only has {item.book.stock_count} copies left."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        total = cart.get_total()
        order = Order.objects.create(
            user=request.user, order_type="cart", status="pending", total_amount=total
        )

        # Save shipping address
        ShippingAddress.objects.create(
            order=order, **serializer.validated_data["shipping_address"]
        )

        for item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                item_type="physical_book",
                book=item.book,
                quantity=item.quantity,
                unit_price=item.book.physical_price,
                total_price=item.get_total_price(),
            )

        # Create Stripe PaymentIntent
        intent = create_payment_intent(
            amount=total,
            metadata={
                "order_id": order.id,
                "user_id": request.user.id,
            },
        )

        order.payment_reference = intent["id"]
        order.save(update_fields=["payment_reference"])

        return Response(
            {
                "order": OrderSerializer(order).data,
                "client_secret": intent["client_secret"],
                "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    """
    Stripe sends signed events here after payment.
    Must be csrf_exempt — Stripe signs requests with its own signature.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

        try:
            event = construct_webhook_event(payload, sig_header)
        except ValueError:
            return Response(
                {"error": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST
            )
        except stripe_lib.error.SignatureVerificationError:
            return Response(
                {"error": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST
            )

        if event["type"] == "payment_intent.succeeded":
            self._handle_payment_success(event["data"]["object"])
        elif event["type"] == "payment_intent.payment_failed":
            self._handle_payment_failed(event["data"]["object"])

        return Response({"status": "ok"})

    def _handle_payment_success(self, intent):
        metadata = getattr(intent, "metadata", {})
        order_id = metadata["order_id"]
        if not order_id:
            return
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return

        order.status = "completed"
        order.save()
        self._fulfill_order(order)

    def _handle_payment_failed(self, intent):
        order_id = intent["metadata"].get("order_id")
        if not order_id:
            return
        try:
            order = Order.objects.get(id=order_id)
            order.status = "failed"
            order.save()
        except Order.DoesNotExist:
            return

    def _fulfill_order(self, order):
        for item in order.items.all():
            if item.item_type == "physical_book":
                item.book.stock_count -= item.quantity
                item.book.save(update_fields=["stock_count"])

            elif item.item_type == "digital_book":
                send_email(
                    to_email=order.user.email,
                    purpose="book_purchase",
                    template_data={
                        "first_name": order.user.first_name or "there",
                        "book_title": item.book.title,
                        "format": "Digital",
                        "amount": str(order.total_amount),
                    },
                )

            elif item.item_type == "course":
                send_email(
                    to_email=order.user.email,
                    purpose="course_purchase",
                    template_data={
                        "first_name": order.user.first_name or "there",
                        "course_name": item.course.title,
                        "amount": str(order.total_amount),
                    },
                )

        if order.order_type == "cart":
            Cart.objects.filter(user=order.user).first().items.all().delete()
            send_email(
                to_email=order.user.email,
                purpose="book_purchase",
                template_data={
                    "first_name": order.user.first_name or "there",
                    "book_title": ", ".join(
                        item.book.title for item in order.items.all()
                    ),
                    "format": "Physical",
                    "amount": str(order.total_amount),
                },
            )


class BookSalesViewSet(viewsets.ViewSet):
    """
    Admin-only — book sales dashboard.
    """

    permission_classes = [IsAdminRole]

    @extend_schema(responses={200: BookSaleSerializer(many=True)})
    def list(self, request):
        """
        GET /orders/book-sales/
        Returns all book order items with full sales info.
        Supports filtering by type, status, and date range.
        """
        queryset = (
            OrderItem.objects.filter(item_type__in=["physical_book", "digital_book"])
            .select_related("order", "order__user", "order__shipping_address", "book")
            .order_by("-order__created_at")
        )

        # Filter by type
        item_type = request.query_params.get("type")
        if item_type in ["physical_book", "digital_book"]:
            queryset = queryset.filter(item_type=item_type)

        # Filter by payment status
        payment_status = request.query_params.get("status")
        if payment_status in ["pending", "completed", "failed"]:
            queryset = queryset.filter(order__status=payment_status)

        # Filter by date range
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if date_from:
            queryset = queryset.filter(order__created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(order__created_at__date__lte=date_to)

        # Search by student email or book title
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(order__user__email__icontains=search)
                | models.Q(book__title__icontains=search)
            )

        serializer = BookSaleSerializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(responses={200: BookSaleSerializer})
    def retrieve(self, request, pk=None):
        """
        GET /orders/book-sales/{order_id}/
        Returns detail for a specific book order including shipping address.
        """
        try:
            item = OrderItem.objects.select_related(
                "order", "order__user", "order__shipping_address", "book"
            ).get(order__id=pk, item_type__in=["physical_book", "digital_book"])
        except OrderItem.DoesNotExist:
            return Response(
                {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(BookSaleSerializer(item).data)

    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """
        GET /orders/book-sales/summary/
        Returns aggregated sales stats for the dashboard header.
        """
        from django.db.models import Count, Sum

        base_qs = OrderItem.objects.filter(
            item_type__in=["physical_book", "digital_book"], order__status="completed"
        )

        stats = base_qs.aggregate(
            total_revenue=Sum("total_price"),
            total_orders=Count("id"),
        )

        physical_stats = base_qs.filter(item_type="physical_book").aggregate(
            count=Count("id"),
            revenue=Sum("total_price"),
        )

        digital_stats = base_qs.filter(item_type="digital_book").aggregate(
            count=Count("id"),
            revenue=Sum("total_price"),
        )

        return Response(
            {
                "total_revenue": stats["total_revenue"] or 0,
                "total_orders": stats["total_orders"] or 0,
                "physical": {
                    "count": physical_stats["count"] or 0,
                    "revenue": physical_stats["revenue"] or 0,
                },
                "digital": {
                    "count": digital_stats["count"] or 0,
                    "revenue": digital_stats["revenue"] or 0,
                },
            }
        )
