import logging
import stripe as stripe_lib

logger = logging.getLogger(__name__)
from django.conf import settings
from django.db import models
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.pagination import StandardPagination
from config.permissions import IsAdminRole
from courses.models import Enrollment
from config.tasks import send_email_task, create_zoom_meeting_for_slot_task, create_lulu_print_job_task
from orders.models import ShippingAddress
from orders.serializers import BookSaleSerializer, UpdateFulfillmentSerializer
from orders.stripe import construct_webhook_event, create_checkout_session, create_payment_intent

from .models import Cart, CartItem, Order, OrderItem
from .serializers import (
    AddToCartSerializer,
    CartCheckoutSerializer,
    CartItemReadSerializer,
    CartSerializer,
    DirectPurchaseSerializer,
    OrderSerializer,
)
from .utils import already_owns


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
        serializer = AddToCartSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        item_type = serializer.validated_data["item_type"]
        obj = serializer.validated_data["object"]
        quantity = serializer.validated_data.get("quantity", 1)

        course = obj if item_type == CartItem.ItemType.COURSE else None
        bundle = obj if item_type == CartItem.ItemType.BUNDLE else None
        book = obj if item_type in (CartItem.ItemType.DIGITAL_BOOK, CartItem.ItemType.PHYSICAL_BOOK) else None

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
    @action(detail=True, methods=["patch"], url_path="fulfillment", permission_classes=[IsAdminRole])
    def update_fulfillment(self, request, pk=None):
        """PATCH /orders/{id}/fulfillment/ — admin updates delivery status."""
        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        if order.fulfillment_status == Order.FulfillmentStatus.NOT_APPLICABLE:
            return Response(
                {"error": "This order has no physical items requiring fulfillment tracking."},
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

        order = Order.objects.create(
            user=request.user,
            order_type=Order.OrderType.DIRECT,
            status=Order.PaymentStatus.PENDING,
            total_amount=price,
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
            total_price=price,
        )

        # Free item (100% scholarship or free course/book) — skip Stripe entirely
        if price == 0:
            order.status = Order.PaymentStatus.COMPLETED
            order.save(update_fields=["status"])
            self._fulfill_order(order)
            return Response(
                {"order": OrderSerializer(order).data},
                status=status.HTTP_201_CREATED,
            )

        # Create Stripe Checkout Session
        session = create_checkout_session(
            line_items=[{
                "price_data": {
                    "currency": settings.CURRENCY,
                    "unit_amount": int(price * 100),
                    "product_data": {"name": obj.name if item_type == "bundle" else obj.title},
                },
                "quantity": 1,
            }],
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

    @extend_schema(request=CartCheckoutSerializer, responses={201: OrderSerializer})
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
        has_physical = any(i.item_type == CartItem.ItemType.PHYSICAL_BOOK for i in items)

        if has_physical and not serializer.validated_data.get("shipping_address"):
            return Response(
                {"error": "shipping_address is required for orders containing physical books."},
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

        total = cart.get_total()
        fulfillment_status = (
            Order.FulfillmentStatus.PROCESSING
            if has_physical
            else Order.FulfillmentStatus.NOT_APPLICABLE
        )
        order = Order.objects.create(
            user=request.user,
            order_type=Order.OrderType.CART,
            status=Order.PaymentStatus.PENDING,
            total_amount=total,
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
            book = item.book if item.item_type in (CartItem.ItemType.DIGITAL_BOOK, CartItem.ItemType.PHYSICAL_BOOK) else None

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
            stripe_line_items.append({
                "price_data": {
                    "currency": settings.CURRENCY,
                    "unit_amount": int(unit_price * 100),
                    "product_data": {"name": item.get_display_name()},
                },
                "quantity": item.quantity,
            })

        # Free cart (e.g. 100% scholarship applied prior) — skip Stripe
        if total == 0:
            order.status = Order.PaymentStatus.COMPLETED
            order.save(update_fields=["status"])
            self._fulfill_order(order)
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
                logger.error(f"Webhook checkout session expired error: {e}", exc_info=True)
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
            self._fulfill_order(order)

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
                Donation.objects.filter(id=donation_id, status=Donation.Status.PENDING).update(
                    status=Donation.Status.COMPLETED
                )
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
        self._fulfill_order(order)

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
                Donation.objects.filter(id=donation_id, status=Donation.Status.PENDING).update(
                    status=Donation.Status.FAILED
                )
            return

        if purchase_type == "consultation":
            purchase_id = metadata.get("consultation_purchase_id")
            if purchase_id:
                from consultations.models import ConsultationPurchase
                ConsultationPurchase.objects.filter(id=purchase_id, status="pending").update(status="failed")
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
                ConsultationPurchase.objects.filter(id=purchase_id).update(status="failed")
        elif purchase_type == "membership":
            membership_id = metadata.get("membership_id")
            if membership_id:
                from memberships.models import UserMembership
                UserMembership.objects.filter(id=membership_id).update(status=UserMembership.Status.FAILED)
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
            purchase = ConsultationPurchase.objects.select_related(
                "student", "consultation"
            ).prefetch_related("booked_slots").get(id=purchase_id)
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
            membership = UserMembership.objects.select_related("user", "plan").get(id=membership_id)
        except UserMembership.DoesNotExist:
            return

        now = timezone.now()
        duration = membership.plan.duration_days if membership.plan else 30
        membership.status = UserMembership.Status.ACTIVE
        membership.start_date = now
        membership.end_date = now + timedelta(days=duration)
        membership.save(update_fields=["status", "start_date", "end_date", "updated_at"])

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
        from django.db import transaction
        with transaction.atomic():
            for item in order.items.select_related("course", "bundle", "book").all():
                if item.item_type == "physical_book":
                    item.book.stock_count -= item.quantity
                    item.book.save(update_fields=["stock_count"])
                    # Dispatch Lulu print job (prints & ships to customer)
                    if item.book.lulu_pod_package_id and item.book.interior_pdf_url:
                        try:
                            create_lulu_print_job_task.delay(item.id)
                        except Exception as e:
                            logger.error("Failed to queue Lulu task for OrderItem %s: %s", item.id, e)

                elif item.item_type == "digital_book":
                    send_email_task.delay(
                        to_email=order.user.email,
                        purpose="book_purchase",
                        template_data={
                            "first_name": order.user.first_name or "there",
                            "book_title": item.book.title,
                            "format": "Digital",
                            "amount": str(order.total_amount),
                        },
                    )
                    logger.info(
                        "Queued book_purchase email to %s for book %s",
                        order.user.email,
                        item.book.title,
                    )

                elif item.item_type == "course":
                    Enrollment.objects.get_or_create(user=order.user, course=item.course)
                    send_email_task.delay(
                        to_email=order.user.email,
                        purpose="course_purchase",
                        template_data={
                            "first_name": order.user.first_name or "there",
                            "course_name": item.course.title,
                            "amount": str(order.total_amount),
                        },
                    )
                    logger.info(
                        "Queued course_purchase email to %s for course %s",
                        order.user.email,
                        item.course.title,
                    )

                elif item.item_type == "bundle":
                    bundle = item.bundle
                    courses = list(bundle.courses.all())
                    for course in courses:
                        Enrollment.objects.get_or_create(user=order.user, course=course)
                    course_names = ", ".join(c.title for c in courses)
                    send_email_task.delay(
                        to_email=order.user.email,
                        purpose="bundle_purchase",
                        template_data={
                            "first_name": order.user.first_name or "there",
                            "bundle_name": bundle.name,
                            "course_names": course_names,
                            "amount": str(order.total_amount),
                        },
                    )
                    logger.info(
                        "Queued bundle_purchase email to %s for bundle %s",
                        order.user.email,
                        bundle.name,
                    )

            if order.order_type == Order.OrderType.CART:
                # Clear cart after fulfillment
                cart = Cart.objects.filter(user=order.user).first()
                if cart:
                    cart.items.all().delete()

                # Send shipping notification only for physical items
                physical_items = [
                    i for i in order.items.all() if i.item_type == "physical_book"
                ]
                if physical_items:
                    send_email_task.delay(
                        to_email=order.user.email,
                        purpose="book_purchase",
                        template_data={
                            "first_name": order.user.first_name or "there",
                            "book_title": ", ".join(i.book.title for i in physical_items),
                            "format": "Physical",
                            "amount": str(order.total_amount),
                        },
                    )
                    logger.info(
                        "Queued physical book_purchase email to %s for order %s",
                        order.user.email,
                        order.id,
                    )




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
                return Response({"error": "Missing id or status."}, status=status.HTTP_400_BAD_REQUEST)

            our_status = self.STATUS_MAP.get(lulu_status.upper())
            if not our_status:
                return Response({"status": "ignored"})

            item = OrderItem.objects.filter(lulu_print_job_id=print_job_id).select_related("order").first()
            if not item:
                logger.warning("LuluWebhook: no OrderItem found for print_job_id=%s", print_job_id)
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
            return Response({"status": "ok"})

        except Exception as e:
            logger.error("LuluWebhook error: %s", e, exc_info=True)
            return Response({"error": "Internal error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
