import logging
import stripe as stripe_lib

from django.conf import settings
from django.db import models
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
    OpenApiResponse,
    OpenApiParameter,
)
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.pagination import StandardPagination
from config.permissions import IsAdminRole
from courses.models import Enrollment
from config.tasks import (
    send_email_task,
    create_zoom_meeting_for_slot_task,
    create_lulu_print_job_task,
)
from consultations.models import ConsultationPurchase
from donations.models import Donation
from memberships.models import UserMembership
from orders.models import ShippingAddress
from orders.lulu import calculate_shipping_cost
from orders.serializers import BookSaleSerializer, UpdateFulfillmentSerializer
from orders.stripe import (
    construct_webhook_event,
    create_checkout_session,
    create_payment_intent,
)

from .models import Cart, CartItem, Coupon, Order, OrderItem
from .serializers import (
    AddToCartSerializer,
    CartCheckoutSerializer,
    CartItemReadSerializer,
    CartSerializer,
    CouponSerializer,
    CouponValidateSerializer,
    DirectPurchaseSerializer,
    OrderSerializer,
)
from .utils import already_owns, fulfill_order

logger = logging.getLogger(__name__)


def _resolve_coupon(coupon_code: str):
    """Return (coupon, error_str). coupon is None if code blank or invalid."""
    if not coupon_code:
        return None, None
    try:
        coupon = Coupon.objects.get(code__iexact=coupon_code.strip())
    except Coupon.DoesNotExist:
        return None, "Invalid coupon code."
    if not coupon.is_valid():
        return None, "This coupon is expired or inactive."
    return coupon, None


class CartViewSet(viewsets.ViewSet):
    """Unified cart — supports courses, bundles, digital books, and physical books."""

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

    @extend_schema(request=AddToCartSerializer, responses={201: CartItemReadSerializer})
    def create(self, request):
        """POST /cart/items/ — add any product to cart."""
        cart = self.get_or_create_cart(request.user)
        serializer = AddToCartSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        item_type = serializer.validated_data["item_type"]
        obj = serializer.validated_data["object"]
        quantity = serializer.validated_data.get("quantity", 1)

        course = obj if item_type == CartItem.ItemType.COURSE else None
        bundle = obj if item_type == CartItem.ItemType.BUNDLE else None
        book = (
            obj
            if item_type
            in (CartItem.ItemType.DIGITAL_BOOK, CartItem.ItemType.PHYSICAL_BOOK)
            else None
        )

        # Enforce one item per product per type in cart
        existing = CartItem.objects.filter(
            cart=cart,
            item_type=item_type,
            course=course,
            bundle=bundle,
            book=book,
        ).first()

        if existing:
            if item_type == CartItem.ItemType.PHYSICAL_BOOK:
                existing.quantity += quantity
                existing.save(update_fields=["quantity"])
                item = existing
            else:
                return Response(
                    {"error": "This item is already in your cart."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            item = CartItem.objects.create(
                cart=cart,
                item_type=item_type,
                course=course,
                bundle=bundle,
                book=book,
                quantity=quantity,
            )

        return Response(
            CartItemReadSerializer(item, context={"request": request}).data,
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

    @extend_schema(
        request=AddToCartSerializer,
        responses={200: CartItemReadSerializer},
    )
    def partial_update(self, request, pk=None):
        """PATCH /cart/items/{id}/ — update quantity (physical books only)."""
        cart = self.get_or_create_cart(request.user)
        try:
            item = CartItem.objects.get(id=pk, cart=cart)
        except CartItem.DoesNotExist:
            return Response(
                {"error": "Item not found in cart."}, status=status.HTTP_404_NOT_FOUND
            )

        if item.item_type != CartItem.ItemType.PHYSICAL_BOOK:
            return Response(
                {"error": "Quantity can only be updated for physical books."},
                status=status.HTTP_400_BAD_REQUEST,
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
        item.save(update_fields=["quantity"])
        return Response(CartItemReadSerializer(item, context={"request": request}).data)

    @extend_schema(responses={204: None})
    @action(detail=False, methods=["delete"], url_path="clear")
    def clear(self, request):
        """DELETE /cart/clear/ — empty cart."""
        cart = self.get_or_create_cart(request.user)
        cart.items.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=inline_serializer(
            "ShippingEstimateRequestSerializer",
            fields={
                "country_code": serializers.CharField(
                    help_text="2-letter ISO country code (e.g. 'US', 'GB', 'KW')"
                ),
                "city": serializers.CharField(help_text="City name"),
                "street1": serializers.CharField(help_text="Street address line 1"),
                "postal_code": serializers.CharField(help_text="Postal / ZIP code"),
                "phone": serializers.CharField(
                    help_text="Phone number (e.g. '+15551234567')"
                ),
                "state_code": serializers.CharField(
                    required=False,
                    help_text="State/province code (e.g. 'NY'). Required for US/CA.",
                ),
                "shipping_level": serializers.ChoiceField(
                    choices=["MAIL", "PRIORITY_MAIL", "GROUND", "EXPEDITED", "EXPRESS"],
                    default="MAIL",
                    help_text="Lulu shipping speed level",
                ),
            },
        ),
        responses={
            200: inline_serializer(
                "ShippingEstimateResponseSerializer",
                fields={
                    "country_code": serializers.CharField(),
                    "shipping_level": serializers.CharField(),
                    "shipping_cost": serializers.DecimalField(
                        max_digits=10,
                        decimal_places=2,
                        help_text="Shipping cost excluding tax (USD)",
                    ),
                    "shipping_cost_incl_tax": serializers.DecimalField(
                        max_digits=10,
                        decimal_places=2,
                        help_text="Shipping cost including tax (USD)",
                    ),
                    "currency": serializers.CharField(),
                },
            ),
            400: OpenApiResponse(
                description="No physical books in cart, missing fields, or invalid country_code"
            ),
            502: OpenApiResponse(description="Lulu API unavailable"),
        },
        summary="Estimate shipping cost",
        description=(
            "Returns the Lulu shipping cost for all physical books in the cart "
            "for the given destination and shipping level. "
            "Accepts the same address fields as checkout. "
            "Call this before checkout to show the user the shipping cost."
        ),
    )
    @action(detail=False, methods=["post"], url_path="estimate-shipping")
    def estimate_shipping(self, request):
        """
        POST /cart/estimate-shipping/
        Returns Lulu shipping cost for the physical books in the cart.
        """
        country_code = request.data.get("country_code", "").strip().upper()
        city = request.data.get("city", "").strip()
        street1 = request.data.get("street1", "").strip()
        postal_code = request.data.get("postal_code", "").strip()
        phone = request.data.get("phone", "").strip()
        state_code = request.data.get("state_code", "").strip()
        shipping_level = request.data.get("shipping_level", "MAIL").strip().upper()

        if not country_code or len(country_code) != 2:
            return Response(
                {
                    "error": "country_code must be a 2-letter ISO code (e.g. 'US', 'GB')."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not city:
            return Response(
                {"error": "city is required for shipping estimate."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart = Cart.objects.filter(user=request.user).first()
        physical_items = [
            i
            for i in (cart.items.select_related("book").all() if cart else [])
            if i.item_type == CartItem.ItemType.PHYSICAL_BOOK
        ]

        if not physical_items:
            return Response(
                {"error": "No physical books in your cart."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        missing = [
            i.book.title
            for i in physical_items
            if not i.book.page_count or not i.book.lulu_pod_package_id
        ]
        if missing:
            return Response(
                {
                    "error": "Some books are missing Lulu configuration and cannot be estimated.",
                    "books": missing,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        lulu_line_items = [
            {
                "pod_package_id": i.book.lulu_pod_package_id,
                "page_count": i.book.page_count,
                "quantity": i.quantity,
            }
            for i in physical_items
        ]

        import requests as req_lib

        try:
            result = calculate_shipping_cost(
                line_items=lulu_line_items,
                country_code=country_code,
                city=city,
                street1=street1,
                postcode=postal_code,
                phone_number=phone,
                state_code=state_code,
                shipping_level=shipping_level,
            )
        except req_lib.HTTPError as exc:
            logger.error("Lulu shipping estimate failed: %s", exc)
            if exc.response is not None and exc.response.status_code == 400:
                # Surface Lulu validation errors to the caller
                try:
                    lulu_errors = exc.response.json()
                    # Flatten nested error messages from Lulu's response
                    messages = []
                    for _field, detail in lulu_errors.items():
                        if isinstance(detail, dict):
                            errors = detail.get("detail", {}).get("errors", [])
                            for e in errors:
                                messages.append(e.get("message", str(e)))
                        else:
                            messages.append(str(detail))
                    return Response(
                        {
                            "error": " | ".join(messages)
                            if messages
                            else "Invalid address for Lulu shipping."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                except Exception:
                    pass
            return Response(
                {
                    "error": "Could not retrieve shipping estimate from Lulu. Please try again."
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:
            logger.error("Lulu shipping estimate failed: %s", exc, exc_info=True)
            return Response(
                {
                    "error": "Could not retrieve shipping estimate from Lulu. Please try again."
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        shipping = result.get("shipping_cost", {})
        return Response(
            {
                "country_code": country_code,
                "shipping_level": shipping_level,
                "shipping_cost": shipping.get("total_cost_excl_tax", "0.00"),
                "shipping_cost_incl_tax": shipping.get("total_cost_incl_tax", "0.00"),
                "currency": result.get("currency", "USD"),
            }
        )

    @extend_schema(
        request=CouponValidateSerializer,
        responses={200: None},
        summary="Validate a coupon code",
        description="Check if a coupon is valid and preview the discount amount and discounted total.",
    )
    @action(detail=False, methods=["post"], url_path="validate-coupon")
    def validate_coupon(self, request):
        """POST /cart/validate-coupon/ — validate a coupon and preview the discount."""
        serializer = CouponValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]
        total = serializer.validated_data["total"]

        coupon, error = _resolve_coupon(code)
        if error:
            return Response(
                {"valid": False, "error": error}, status=status.HTTP_400_BAD_REQUEST
            )

        from decimal import Decimal

        discount = coupon.calculate_discount(total)
        discounted_total = max(Decimal("0"), Decimal(str(total)) - discount)
        return Response(
            {
                "valid": True,
                "code": coupon.code,
                "discount_type": coupon.discount_type,
                "discount_value": str(coupon.discount_value),
                "discount_amount": str(discount),
                "discounted_total": str(discounted_total),
            }
        )


class OrderViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OrderSerializer(many=True)})
    def list(self, request):
        """GET /orders/ — user's order history (admin sees all)."""
        qs = Order.objects.prefetch_related(
            "items__course",
            "items__book",
            "shipping_address",
        )
        if request.user.role == "admin":
            orders = qs.order_by("-created_at")
        else:
            orders = qs.filter(user=request.user).order_by("-created_at")

        paginator = StandardPagination()
        page = paginator.paginate_queryset(orders, request)
        serializer = OrderSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def retrieve(self, request, pk=None):
        """GET /orders/{id}/"""
        if request.user.role == "admin":
            try:
                order = Order.objects.get(id=pk)
            except Order.DoesNotExist:
                return Response(
                    {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
                )
        else:
            try:
                order = Order.objects.get(id=pk, user=request.user)
            except Order.DoesNotExist:
                return Response(
                    {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
                )
        return Response(OrderSerializer(order).data)

    @extend_schema(
        request=UpdateFulfillmentSerializer,
        responses={200: OrderSerializer},
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path="fulfillment",
        permission_classes=[IsAdminRole],
    )
    def update_fulfillment(self, request, pk=None):
        """PATCH /orders/{id}/fulfillment/ — admin updates delivery status."""
        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if order.fulfillment_status == Order.FulfillmentStatus.NOT_APPLICABLE:
            return Response(
                {
                    "error": "This order has no physical items requiring fulfillment tracking."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = UpdateFulfillmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order.fulfillment_status = serializer.validated_data["fulfillment_status"]
        order.save(update_fields=["fulfillment_status"])
        return Response(OrderSerializer(order).data)

    @extend_schema(request=DirectPurchaseSerializer, responses={201: OrderSerializer})
    @action(detail=False, methods=["post"], url_path="direct")
    def direct_purchase(self, request):
        """
        POST /orders/direct/
        Buy a course, bundle, or digital book directly.
        """
        serializer = DirectPurchaseSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        item_type = serializer.validated_data["item_type"]
        obj = serializer.validated_data["object"]
        price = serializer.validated_data["price"]

        # Resolve coupon
        coupon_code = serializer.validated_data.get("coupon_code", "")
        coupon, coupon_error = _resolve_coupon(coupon_code)
        if coupon_error:
            return Response({"error": coupon_error}, status=status.HTTP_400_BAD_REQUEST)

        from decimal import Decimal

        discount_amount = coupon.calculate_discount(price) if coupon else Decimal("0")
        final_price = max(Decimal("0"), Decimal(str(price)) - discount_amount)

        order = Order.objects.create(
            user=request.user,
            order_type=Order.OrderType.DIRECT,
            status=Order.PaymentStatus.PENDING,
            coupon=coupon,
            discount_amount=discount_amount,
            total_amount=final_price,
        )

        course = obj if item_type == "course" else None
        bundle = obj if item_type == "bundle" else None
        book = obj if item_type == "digital_book" else None

        OrderItem.objects.create(
            order=order,
            item_type=item_type,
            course=course,
            bundle=bundle,
            book=book,
            unit_price=price,
            total_price=final_price,
        )

        # Free item (100% scholarship, free course/book, or 100% coupon) — skip Stripe entirely
        if final_price == 0:
            order.status = Order.PaymentStatus.COMPLETED
            order.save(update_fields=["status"])
            fulfill_order(order)
            return Response(
                {"order": OrderSerializer(order).data},
                status=status.HTTP_201_CREATED,
            )

        # Create Stripe Checkout Session
        session = create_checkout_session(
            line_items=[
                {
                    "price_data": {
                        "currency": settings.CURRENCY,
                        "unit_amount": int(final_price * 100),
                        "product_data": {
                            "name": obj.name if item_type == "bundle" else obj.title
                        },
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{settings.FRONTEND_URL}/order-complete?order_id={order.id}",
            cancel_url=f"{settings.FRONTEND_URL}/checkout?cancelled=true",
            metadata={"order_id": order.id, "user_id": request.user.id},
        )

        # Save Checkout Session ID as payment reference
        order.payment_reference = session["id"]
        order.save(update_fields=["payment_reference"])

        return Response(
            {
                "order": OrderSerializer(order).data,
                "checkout_url": session["url"],
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=CartCheckoutSerializer,
        responses={
            201: OrderSerializer,
            400: OpenApiResponse(
                description="Cart empty, missing shipping_address, or insufficient stock"
            ),
        },
        summary="Checkout cart",
        description=(
            "Checkout the full cart — courses, bundles, digital books, and physical books.\n\n"
            "`shipping_address` and `shipping_level` are required when the cart contains physical books.\n\n"
            "For physical books, the Lulu shipping cost is fetched automatically and added as a "
            "separate line item in the Stripe checkout session. "
            "Call `POST /cart/estimate-shipping/` first to show the user the shipping cost before they confirm.\n\n"
            "**Shipping levels:** `MAIL` (default), `PRIORITY_MAIL`, `GROUND`, `EXPEDITED`, `EXPRESS`"
        ),
    )
    @action(detail=False, methods=["post"], url_path="checkout")
    def checkout(self, request):
        """
        POST /orders/checkout/
        Checkout the full cart — courses, bundles, digital books, and physical books.
        shipping_address is required only when the cart contains physical books.
        """
        serializer = CartCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = Cart.objects.filter(user=request.user).first()
        if not cart or not cart.items.exists():
            return Response(
                {"error": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST
            )

        items = list(cart.items.select_related("course", "bundle", "book").all())
        has_physical = any(
            i.item_type == CartItem.ItemType.PHYSICAL_BOOK for i in items
        )

        if has_physical and not serializer.validated_data.get("shipping_address"):
            return Response(
                {
                    "error": "shipping_address is required for orders containing physical books."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate stock for physical items
        for item in items:
            if item.item_type == CartItem.ItemType.PHYSICAL_BOOK:
                if item.quantity > item.book.stock_count:
                    return Response(
                        {
                            "error": f"'{item.book.title}' only has {item.book.stock_count} copies left."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Calculate Lulu shipping cost for physical books
        from decimal import Decimal

        shipping_cost = Decimal("0")
        shipping_level = serializer.validated_data.get("shipping_level", "MAIL")
        if has_physical:
            physical_items = [
                i for i in items if i.item_type == CartItem.ItemType.PHYSICAL_BOOK
            ]
            lulu_line_items = [
                {
                    "pod_package_id": i.book.lulu_pod_package_id,
                    "page_count": i.book.page_count,
                    "quantity": i.quantity,
                }
                for i in physical_items
                if i.book.lulu_pod_package_id and i.book.page_count
            ]
            if lulu_line_items:
                addr = serializer.validated_data["shipping_address"]
                try:
                    cost_result = calculate_shipping_cost(
                        line_items=lulu_line_items,
                        country_code=addr["country"],
                        city=addr.get("city", ""),
                        street1=addr.get("address_line", ""),
                        postcode=addr.get("postal_code", ""),
                        phone_number=addr.get("phone", ""),
                        shipping_level=shipping_level,
                    )
                    shipping_cost = Decimal(
                        str(
                            cost_result.get("shipping_cost", {}).get(
                                "total_cost_excl_tax", 0
                            )
                        )
                    )
                except Exception as exc:
                    logger.warning("Lulu shipping cost fetch failed: %s", exc)
                    # Non-blocking — proceed without shipping cost if Lulu is unavailable

        total = cart.get_total() + shipping_cost

        # Resolve coupon
        coupon_code = serializer.validated_data.get("coupon_code", "")
        coupon, coupon_error = _resolve_coupon(coupon_code)
        if coupon_error:
            return Response({"error": coupon_error}, status=status.HTTP_400_BAD_REQUEST)

        discount_amount = coupon.calculate_discount(total) if coupon else Decimal("0")
        final_total = max(Decimal("0"), total - discount_amount)

        fulfillment_status = (
            Order.FulfillmentStatus.PROCESSING
            if has_physical
            else Order.FulfillmentStatus.NOT_APPLICABLE
        )
        order = Order.objects.create(
            user=request.user,
            order_type=Order.OrderType.CART,
            status=Order.PaymentStatus.PENDING,
            coupon=coupon,
            discount_amount=discount_amount,
            total_amount=final_total,
            shipping_cost=shipping_cost,
            fulfillment_status=fulfillment_status,
        )

        if has_physical:
            ShippingAddress.objects.create(
                order=order, **serializer.validated_data["shipping_address"]
            )

        stripe_line_items = []
        for item in items:
            unit_price = item.get_unit_price()
            total_price = item.get_total_price()
            course = item.course if item.item_type == CartItem.ItemType.COURSE else None
            bundle = item.bundle if item.item_type == CartItem.ItemType.BUNDLE else None
            book = (
                item.book
                if item.item_type
                in (CartItem.ItemType.DIGITAL_BOOK, CartItem.ItemType.PHYSICAL_BOOK)
                else None
            )

            OrderItem.objects.create(
                order=order,
                item_type=item.item_type,
                course=course,
                bundle=bundle,
                book=book,
                quantity=item.quantity,
                unit_price=unit_price,
                total_price=total_price,
            )
            stripe_line_items.append(
                {
                    "price_data": {
                        "currency": settings.CURRENCY,
                        "unit_amount": int(unit_price * 100),
                        "product_data": {"name": item.get_display_name()},
                    },
                    "quantity": item.quantity,
                }
            )

        # Add shipping as a separate Stripe line item
        if shipping_cost > 0:
            stripe_line_items.append(
                {
                    "price_data": {
                        "currency": settings.CURRENCY,
                        "unit_amount": int(shipping_cost * 100),
                        "product_data": {
                            "name": f"Shipping ({shipping_level.replace('_', ' ').title()})"
                        },
                    },
                    "quantity": 1,
                }
            )

        # Add coupon discount as a negative line item so Stripe total matches
        if discount_amount > 0:
            stripe_line_items.append(
                {
                    "price_data": {
                        "currency": settings.CURRENCY,
                        "unit_amount": -int(discount_amount * 100),
                        "product_data": {"name": f"Discount ({coupon.code})"},
                    },
                    "quantity": 1,
                }
            )

        # Free cart — skip Stripe
        if final_total == 0:
            order.status = Order.PaymentStatus.COMPLETED
            order.save(update_fields=["status"])
            fulfill_order(order)
            return Response(
                {"order": OrderSerializer(order).data},
                status=status.HTTP_201_CREATED,
            )

        session = create_checkout_session(
            line_items=stripe_line_items,
            success_url=f"{settings.FRONTEND_URL}/order-complete?order_id={order.id}",
            cancel_url=f"{settings.FRONTEND_URL}/cart?cancelled=true",
            metadata={"order_id": order.id, "user_id": request.user.id},
        )

        order.payment_reference = session["id"]
        order.save(update_fields=["payment_reference"])

        return Response(
            {
                "order": OrderSerializer(order).data,
                "checkout_url": session["url"],
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
            try:
                self._handle_payment_success(event["data"]["object"])
            except Exception as e:
                logger.error(f"Webhook fulfillment error: {e}", exc_info=True)
        elif event["type"] == "checkout.session.completed":
            try:
                self._handle_checkout_session_completed(event["data"]["object"])
            except Exception as e:
                logger.error(f"Webhook checkout session error: {e}", exc_info=True)
        elif event["type"] == "checkout.session.expired":
            try:
                self._handle_checkout_session_expired(event["data"]["object"])
            except Exception as e:
                logger.error(
                    f"Webhook checkout session expired error: {e}", exc_info=True
                )
        elif event["type"] == "payment_intent.payment_failed":
            try:
                self._handle_payment_failed(event["data"]["object"])
            except Exception as e:
                logger.error(f"Webhook failure handler error: {e}", exc_info=True)

        return Response({"status": "ok"})

    def _handle_payment_success(self, intent):
        metadata_raw = getattr(intent, "metadata", None)
        metadata = getattr(metadata_raw, "_data", None) or {}
        purchase_type = metadata.get("purchase_type", "order")

        if purchase_type == "consultation":
            self._fulfill_consultation(metadata)
        elif purchase_type == "membership":
            self._fulfill_membership(metadata)
        elif purchase_type == "donation":
            self._fulfill_donation(metadata)
        else:
            order_id = metadata.get("order_id")
            if not order_id:
                return
            try:
                order = Order.objects.get(id=order_id)
            except Order.DoesNotExist:
                return
            order.status = Order.PaymentStatus.COMPLETED
            order.save()
            fulfill_order(order)

    def _handle_checkout_session_completed(self, session):
        """Fulfills purchases created via Stripe Checkout Sessions."""
        metadata_raw = getattr(session, "metadata", None)
        metadata = getattr(metadata_raw, "_data", None) or {}
        purchase_type = metadata.get("purchase_type", "order")

        if purchase_type == "membership":
            self._fulfill_membership(metadata)
            return

        if purchase_type == "donation":
            donation_id = metadata.get("donation_id")
            if donation_id:
                from donations.models import Donation

                Donation.objects.filter(
                    id=donation_id, status=Donation.Status.PENDING
                ).update(status=Donation.Status.COMPLETED)
            return

        if purchase_type == "consultation":
            self._fulfill_consultation(metadata)
            return

        order_id = metadata.get("order_id")
        if not order_id:
            return
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return
        if order.status == Order.PaymentStatus.COMPLETED:
            return  # idempotency guard
        order.status = Order.PaymentStatus.COMPLETED
        order.save()
        fulfill_order(order)

    def _handle_checkout_session_expired(self, session):
        """Marks the purchase as failed when the Stripe Checkout Session expires."""
        metadata_raw = getattr(session, "metadata", None)
        metadata = getattr(metadata_raw, "_data", None) or {}
        purchase_type = metadata.get("purchase_type", "order")

        if purchase_type == "membership":
            membership_id = metadata.get("membership_id")
            if membership_id:
                from memberships.models import UserMembership

                UserMembership.objects.filter(id=membership_id).update(
                    status=UserMembership.Status.FAILED
                )
            return

        if purchase_type == "donation":
            donation_id = metadata.get("donation_id")
            if donation_id:
                from donations.models import Donation

                Donation.objects.filter(
                    id=donation_id, status=Donation.Status.PENDING
                ).update(status=Donation.Status.FAILED)
            return

        if purchase_type == "consultation":
            purchase_id = metadata.get("consultation_purchase_id")
            if purchase_id:
                from consultations.models import ConsultationPurchase

                ConsultationPurchase.objects.filter(
                    id=purchase_id, status="pending"
                ).update(status="failed")
            return

        order_id = metadata.get("order_id")
        if not order_id:
            return
        try:
            order = Order.objects.get(id=order_id)
            if order.status == Order.PaymentStatus.PENDING:
                order.status = Order.PaymentStatus.FAILED
                order.save()
        except Order.DoesNotExist:
            return

    def _handle_payment_failed(self, intent):
        metadata_raw = getattr(intent, "metadata", None)
        metadata = getattr(metadata_raw, "_data", None) or {}
        purchase_type = metadata.get("purchase_type", "order")

        if purchase_type == "consultation":
            purchase_id = metadata.get("consultation_purchase_id")
            if purchase_id:
                from consultations.models import ConsultationPurchase

                ConsultationPurchase.objects.filter(id=purchase_id).update(
                    status="failed"
                )
        elif purchase_type == "membership":
            membership_id = metadata.get("membership_id")
            if membership_id:
                from memberships.models import UserMembership

                UserMembership.objects.filter(id=membership_id).update(
                    status=UserMembership.Status.FAILED
                )
        else:
            order_id = metadata.get("order_id")
            if not order_id:
                return
            try:
                order = Order.objects.get(id=order_id)
                order.status = Order.PaymentStatus.FAILED
                order.save()
            except Order.DoesNotExist:
                return

    def _fulfill_consultation(self, metadata):
        from consultations.models import ConsultationPurchase

        purchase_id = metadata.get("consultation_purchase_id")
        if not purchase_id:
            return
        try:
            purchase = (
                ConsultationPurchase.objects.select_related("student", "consultation")
                .prefetch_related("booked_slots")
                .get(id=purchase_id)
            )
        except ConsultationPurchase.DoesNotExist:
            return

        purchase.status = "completed"
        purchase.save(update_fields=["status"])

        # Mark timeslots as booked and create Zoom meetings
        for slot in purchase.booked_slots.all():
            slot.is_booked = True
            slot.save(update_fields=["is_booked"])

            try:
                create_zoom_meeting_for_slot_task.delay(
                    slot.id,
                    purchase.consultation.title,
                    purchase.student.first_name or purchase.student.email,
                )
            except Exception as e:
                logger.error(
                    f"Failed to queue Zoom meeting task for slot {slot.pk}: {e}"
                )

        # Send confirmation email
        slot_list = ", ".join(
            f"{s.scheduled_start.strftime('%Y-%m-%d %H:%M')}–{s.scheduled_end.strftime('%H:%M')} UTC"
            for s in purchase.booked_slots.all()
        )
        send_email_task.delay(
            to_email=purchase.student.email,
            purpose="consultation_purchase",
            template_data={
                "first_name": purchase.student.first_name or "there",
                "consultation_title": purchase.consultation.title,
                "sessions": purchase.sessions_purchased,
                "slots": slot_list,
                "amount": str(purchase.total_price_paid),
            },
        )
        logger.info(
            "Queued consultation_purchase email to %s for consultation %s",
            purchase.student.email,
            purchase.consultation.title,
        )

    def _fulfill_membership(self, metadata):
        from memberships.models import UserMembership
        from django.utils import timezone
        from datetime import timedelta

        membership_id = metadata.get("membership_id")
        if not membership_id:
            return
        try:
            membership = UserMembership.objects.select_related("user", "plan").get(
                id=membership_id
            )
        except UserMembership.DoesNotExist:
            return

        now = timezone.now()
        duration = membership.plan.duration_days if membership.plan else 30
        membership.status = UserMembership.Status.ACTIVE
        membership.start_date = now
        membership.end_date = now + timedelta(days=duration)
        membership.save(
            update_fields=["status", "start_date", "end_date", "updated_at"]
        )

        send_email_task.delay(
            to_email=membership.user.email,
            purpose="membership_purchase",
            template_data={
                "first_name": membership.user.first_name or "there",
                "plan_name": membership.plan.name if membership.plan else "Membership",
                "end_date": membership.end_date.strftime("%Y-%m-%d"),
            },
        )
        logger.info(
            "Queued membership_purchase email to %s for plan %s",
            membership.user.email,
            membership.plan.name if membership.plan else "Membership",
        )

    def _fulfill_donation(self, metadata):
        from donations.models import Donation

        donation_id = metadata.get("donation_id")
        if not donation_id:
            return
        Donation.objects.filter(id=donation_id).update(status=Donation.Status.COMPLETED)

    def _fulfill_order(self, order):
        fulfill_order(order)


@method_decorator(csrf_exempt, name="dispatch")
class LuluWebhookView(APIView):
    """
    Lulu sends print job status updates here.
    Maps Lulu statuses to our Order.fulfillment_status.
    """

    permission_classes = [permissions.AllowAny]

    # Lulu status → our FulfillmentStatus
    STATUS_MAP = {
        "CREATED": Order.FulfillmentStatus.PROCESSING,
        "UNPAID": Order.FulfillmentStatus.PROCESSING,
        "PAYMENT_IN_PROGRESS": Order.FulfillmentStatus.PROCESSING,
        "PRODUCTION_READY": Order.FulfillmentStatus.PROCESSING,
        "IN_PRODUCTION": Order.FulfillmentStatus.PROCESSING,
        "SHIPPED": Order.FulfillmentStatus.SHIPPED,
        "DELIVERED": Order.FulfillmentStatus.DELIVERED,
        "CANCELLED": Order.FulfillmentStatus.CANCELLED,
        "REJECTED": Order.FulfillmentStatus.CANCELLED,
        "ERROR": Order.FulfillmentStatus.CANCELLED,
    }

    def post(self, request):
        try:
            data = request.data
            print_job_id = str(data.get("id", ""))
            lulu_status = data.get("status", {})
            if isinstance(lulu_status, dict):
                lulu_status = lulu_status.get("name", "")

            if not print_job_id or not lulu_status:
                return Response(
                    {"error": "Missing id or status."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            our_status = self.STATUS_MAP.get(lulu_status.upper())
            if not our_status:
                return Response({"status": "ignored"})

            item = (
                OrderItem.objects.filter(lulu_print_job_id=print_job_id)
                .select_related("order__user", "book")
                .first()
            )
            if not item:
                logger.warning(
                    "LuluWebhook: no OrderItem found for print_job_id=%s", print_job_id
                )
                return Response({"status": "ok"})

            order = item.order
            order.fulfillment_status = our_status
            order.save(update_fields=["fulfillment_status"])
            logger.info(
                "LuluWebhook: order %s fulfillment_status → %s (lulu_status=%s)",
                order.id,
                our_status,
                lulu_status,
            )

            # Alert admin on rejection
            if lulu_status.upper() in ("REJECTED", "ERROR", "CANCELLED"):
                self._alert_admin(data, item, lulu_status)

            return Response({"status": "ok"})

        except Exception as e:
            logger.error("LuluWebhook error: %s", e, exc_info=True)
            return Response(
                {"error": "Internal error."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _alert_admin(self, data, item, lulu_status):
        from django.conf import settings as django_settings
        from email_templates.sendgrid import send_plain_email

        admin_email = django_settings.ADMIN_EMAIL
        if not admin_email:
            logger.warning(
                "LuluWebhook: ADMIN_EMAIL not set, skipping rejection alert."
            )
            return

        order = item.order
        book_title = item.book.title if item.book else "Unknown"
        line_items = data.get("line_items", [])
        rejection_details = []
        for li in line_items:
            normalization = li.get("printable_normalization") or li.get("tracking", {})
            if normalization:
                rejection_details.append(str(normalization))

        reason = (
            "\n".join(rejection_details)
            if rejection_details
            else "No details provided by Lulu."
        )

        subject = f"⚠️ Lulu Print Job {lulu_status} — Order #{order.id}"
        body = (
            f"A Lulu print job was {lulu_status} for Order #{order.id}.\n\n"
            f"Book: {book_title}\n"
            f"Customer: {order.user.email}\n"
            f"Lulu Print Job ID: {item.lulu_print_job_id}\n\n"
            f"Rejection reason:\n{reason}\n\n"
            f"Review it at: https://developers.sandbox.lulu.com/print-jobs/{item.lulu_print_job_id}"
        )
        try:
            send_plain_email(admin_email, subject, body)
        except Exception as e:
            logger.error("LuluWebhook: failed to send admin alert email: %s", e)


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
        valid_statuses = Order.PaymentStatus.values
        if payment_status in valid_statuses:
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

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = BookSaleSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

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


class SalesViewSet(viewsets.ViewSet):
    """
    Admin-only — unified sales dashboard across all revenue streams.
    """

    permission_classes = [IsAdminRole]

    # ------------------------------------------------------------------ helpers

    def _normalize_order_item(self, item):
        order = item.order
        if item.item_type == "course" and item.course:
            product_name = item.course.title
        elif item.item_type == "bundle" and item.bundle:
            product_name = item.bundle.name
        elif item.item_type in ("digital_book", "physical_book") and item.book:
            product_name = item.book.title
        else:
            product_name = item.item_type

        shipping = None
        if hasattr(order, "shipping_address"):
            sa = order.shipping_address
            shipping = f"{sa.full_name}, {sa.address_line}, {sa.city}, {sa.country}"

        return {
            "id": f"order-item-{item.id}",
            "type": item.item_type,
            "product_name": product_name,
            "student_email": order.user.email,
            "student_name": f"{order.user.first_name} {order.user.last_name}".strip()
            or order.user.email,
            "quantity": item.quantity,
            "amount": str(item.total_price),
            "payment_status": order.status,
            "payment_reference": order.payment_reference,
            "date": order.created_at.isoformat(),
            "shipping_address": shipping,
        }

    def _normalize_consultation(self, cp):
        return {
            "id": f"consultation-{cp.id}",
            "type": "consultation",
            "product_name": cp.consultation.title,
            "student_email": cp.student.email,
            "student_name": f"{cp.student.first_name} {cp.student.last_name}".strip()
            or cp.student.email,
            "quantity": cp.sessions_purchased,
            "amount": str(cp.total_price_paid),
            "payment_status": cp.status,
            "payment_reference": cp.payment_reference,
            "date": cp.created_at.isoformat(),
            "shipping_address": None,
        }

    def _normalize_donation(self, donation):
        return {
            "id": f"donation-{donation.id}",
            "type": "donation",
            "product_name": "Donation",
            "student_email": donation.email,
            "student_name": f"{donation.first_name} {donation.last_name}".strip(),
            "quantity": 1,
            "amount": str(donation.amount),
            "payment_status": donation.status,
            "payment_reference": donation.stripe_reference,
            "date": donation.created_at.isoformat(),
            "shipping_address": None,
        }

    def _normalize_membership(self, um):
        plan_name = um.plan.name if um.plan else "Membership"
        amount = str(um.plan.price) if um.plan else "0"
        return {
            "id": f"membership-{um.id}",
            "type": "membership",
            "product_name": plan_name,
            "student_email": um.user.email,
            "student_name": f"{um.user.first_name} {um.user.last_name}".strip()
            or um.user.email,
            "quantity": 1,
            "amount": amount,
            "payment_status": um.status,
            "payment_reference": um.payment_reference,
            "date": um.created_at.isoformat(),
            "shipping_address": None,
        }

    # ------------------------------------------------------------------ views

    @extend_schema(
        responses={
            200: inline_serializer(
                name="SaleItem",
                fields={
                    "id": serializers.CharField(),
                    "type": serializers.ChoiceField(
                        choices=[
                            "course",
                            "bundle",
                            "digital_book",
                            "physical_book",
                            "consultation",
                            "donation",
                            "membership",
                        ]
                    ),
                    "product_name": serializers.CharField(),
                    "student_email": serializers.EmailField(),
                    "student_name": serializers.CharField(),
                    "quantity": serializers.IntegerField(),
                    "amount": serializers.DecimalField(max_digits=10, decimal_places=2),
                    "payment_status": serializers.CharField(),
                    "payment_reference": serializers.CharField(allow_null=True),
                    "date": serializers.DateTimeField(),
                    "shipping_address": serializers.CharField(allow_null=True),
                },
            )
        },
        parameters=[
            inline_serializer(
                name="SalesFilters",
                fields={
                    "type": serializers.CharField(required=False),
                    "payment_status": serializers.CharField(required=False),
                    "date_from": serializers.DateField(required=False),
                    "date_to": serializers.DateField(required=False),
                    "search": serializers.CharField(required=False),
                },
            )
        ],
    )
    def list(self, request):
        """
        GET /orders/sales/
        Unified paginated list of all sales: courses, bundles, books, consultations, donations, memberships.
        Filters: type, payment_status, date_from, date_to, search (email/name/product).
        """
        sale_type = request.query_params.get("type")
        payment_status = request.query_params.get("payment_status")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        search = request.query_params.get("search", "").strip()

        results = []

        # --- OrderItems (course, bundle, digital_book, physical_book) ---
        if not sale_type or sale_type in (
            "course",
            "bundle",
            "digital_book",
            "physical_book",
        ):
            oi_qs = OrderItem.objects.select_related(
                "order",
                "order__user",
                "order__shipping_address",
                "course",
                "bundle",
                "book",
            ).order_by("-order__created_at")
            if sale_type:
                oi_qs = oi_qs.filter(item_type=sale_type)
            if payment_status:
                oi_qs = oi_qs.filter(order__status=payment_status)
            if date_from:
                oi_qs = oi_qs.filter(order__created_at__date__gte=date_from)
            if date_to:
                oi_qs = oi_qs.filter(order__created_at__date__lte=date_to)
            if search:
                oi_qs = oi_qs.filter(
                    models.Q(order__user__email__icontains=search)
                    | models.Q(order__user__first_name__icontains=search)
                    | models.Q(order__user__last_name__icontains=search)
                    | models.Q(course__title__icontains=search)
                    | models.Q(bundle__name__icontains=search)
                    | models.Q(book__title__icontains=search)
                )
            results.extend(self._normalize_order_item(item) for item in oi_qs)

        # --- ConsultationPurchases ---
        if not sale_type or sale_type == "consultation":
            cp_qs = ConsultationPurchase.objects.select_related(
                "student", "consultation"
            ).order_by("-created_at")
            if payment_status:
                cp_qs = cp_qs.filter(status=payment_status)
            if date_from:
                cp_qs = cp_qs.filter(created_at__date__gte=date_from)
            if date_to:
                cp_qs = cp_qs.filter(created_at__date__lte=date_to)
            if search:
                cp_qs = cp_qs.filter(
                    models.Q(student__email__icontains=search)
                    | models.Q(student__first_name__icontains=search)
                    | models.Q(student__last_name__icontains=search)
                    | models.Q(consultation__title__icontains=search)
                )
            results.extend(self._normalize_consultation(cp) for cp in cp_qs)

        # --- Donations ---
        if not sale_type or sale_type == "donation":
            don_qs = Donation.objects.order_by("-created_at")
            if payment_status:
                don_qs = don_qs.filter(status=payment_status)
            if date_from:
                don_qs = don_qs.filter(created_at__date__gte=date_from)
            if date_to:
                don_qs = don_qs.filter(created_at__date__lte=date_to)
            if search:
                don_qs = don_qs.filter(
                    models.Q(email__icontains=search)
                    | models.Q(first_name__icontains=search)
                    | models.Q(last_name__icontains=search)
                )
            results.extend(self._normalize_donation(d) for d in don_qs)

        # --- UserMemberships ---
        if not sale_type or sale_type == "membership":
            mem_qs = UserMembership.objects.select_related("user", "plan").order_by(
                "-created_at"
            )
            if payment_status:
                mem_qs = mem_qs.filter(status=payment_status)
            if date_from:
                mem_qs = mem_qs.filter(created_at__date__gte=date_from)
            if date_to:
                mem_qs = mem_qs.filter(created_at__date__lte=date_to)
            if search:
                mem_qs = mem_qs.filter(
                    models.Q(user__email__icontains=search)
                    | models.Q(user__first_name__icontains=search)
                    | models.Q(user__last_name__icontains=search)
                    | models.Q(plan__name__icontains=search)
                )
            results.extend(self._normalize_membership(um) for um in mem_qs)

        # Sort merged results by date descending
        results.sort(key=lambda x: x["date"], reverse=True)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(results, request)
        return paginator.get_paginated_response(page)

    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """
        GET /orders/sales/summary/
        Revenue breakdown by sale type (completed/active payments only).
        """
        from django.db.models import Count, Sum

        # Order items
        oi_base = OrderItem.objects.filter(order__status="completed")
        course_stats = oi_base.filter(item_type="course").aggregate(
            count=Count("id"), revenue=Sum("total_price")
        )
        bundle_stats = oi_base.filter(item_type="bundle").aggregate(
            count=Count("id"), revenue=Sum("total_price")
        )
        digital_stats = oi_base.filter(item_type="digital_book").aggregate(
            count=Count("id"), revenue=Sum("total_price")
        )
        physical_stats = oi_base.filter(item_type="physical_book").aggregate(
            count=Count("id"), revenue=Sum("total_price")
        )

        # Consultations
        cp_stats = ConsultationPurchase.objects.filter(status="completed").aggregate(
            count=Count("id"), revenue=Sum("total_price_paid")
        )

        # Donations
        don_stats = Donation.objects.filter(status="completed").aggregate(
            count=Count("id"), revenue=Sum("amount")
        )

        # Memberships (active = paid)
        mem_stats = UserMembership.objects.filter(
            status__in=["active", "expired"]
        ).aggregate(count=Count("id"), revenue=Sum("plan__price"))

        def _fmt(stats, rev_key="revenue"):
            return {
                "count": stats["count"] or 0,
                "revenue": str(stats[rev_key] or 0),
            }

        total_revenue = (
            (course_stats["revenue"] or 0)
            + (bundle_stats["revenue"] or 0)
            + (digital_stats["revenue"] or 0)
            + (physical_stats["revenue"] or 0)
            + (cp_stats["revenue"] or 0)
            + (don_stats["revenue"] or 0)
            + (mem_stats["revenue"] or 0)
        )

        return Response(
            {
                "total_revenue": str(total_revenue),
                "breakdown": {
                    "course": _fmt(course_stats),
                    "bundle": _fmt(bundle_stats),
                    "digital_book": _fmt(digital_stats),
                    "physical_book": _fmt(physical_stats),
                    "consultation": _fmt(cp_stats),
                    "donation": _fmt(don_stats),
                    "membership": _fmt(mem_stats),
                },
            }
        )


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="search",
            description="Case-insensitive search for coupon code",
            required=False,
            type=str,
            location=OpenApiParameter.QUERY,
        ),
    ]
)
class CouponViewSet(viewsets.ModelViewSet):
    """Admin CRUD for coupons. GET list/detail is admin-only."""

    serializer_class = CouponSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        qs = Coupon.objects.all().order_by("-created_at")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(code__icontains=search)
        return qs
