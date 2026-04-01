from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from orders.models import ShippingAddress

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

        # TODO: initiate payment gateway here
        # For now return pending order
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

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

        # TODO: initiate payment gateway here
        # Cart is cleared after payment confirmation, not here
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @extend_schema(exclude=True)  # hide webhook from public docs
    @action(detail=False, methods=["post"], url_path="webhook")
    def webhook(self, request):
        """
        POST /orders/webhook/
        Payment gateway webhook — mark order as completed.
        Plug in your gateway verification logic here.
        """
        payment_reference = request.data.get("payment_reference")
        payment_status = request.data.get("status")

        try:
            order = Order.objects.get(payment_reference=payment_reference)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if payment_status == "success":
            order.status = "completed"
            order.save()
            self._fulfill_order(order)
        else:
            order.status = "failed"
            order.save()

        return Response({"detail": "Webhook received."})

    def _fulfill_order(self, order):
        """Post-payment fulfillment per item type."""
        for item in order.items.all():
            if item.item_type == "physical_book":
                # Decrement stock
                item.book.stock_count -= item.quantity
                item.book.save(update_fields=["stock_count"])
                # TODO: create PhysicalDelivery record here

            elif item.item_type == "digital_book":
                pass  # access granted via has_access() check

            elif item.item_type == "course":
                pass  # enrollment granted via has_access() check

        # Clear cart after successful physical book order
        if order.order_type == "cart":
            Cart.objects.filter(user=order.user).first().items.all().delete()
