from django.conf import settings
from django.db import transaction
import logging
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import permissions, serializers as drf_serializers, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from config.permissions import IsAdminRole, IsTeacherRole
from orders.stripe import create_checkout_session

from .models import AvailableTimeslot, Bundle, Consultation, ConsultationPurchase, RecurringAvailability
from .serializers import (
    AvailableTimeslotSerializer,
    ConsultationBookSerializer,
    ConsultationBundleSerializer,
    ConsultationPurchaseSerializer,
    ConsultationSerializer,
    RecurringAvailabilitySerializer,
    TimeslotSlimSerializer,
)


class ConsultationViewSet(viewsets.ModelViewSet):
    queryset = (
        Consultation.objects.select_related("teacher", "teacher__user")
        .prefetch_related("timeslots", "bundles", "recurring_rules")
        .all()
    )
    serializer_class = ConsultationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {"teacher": ["exact"], "teacher__user__email": ["icontains", "exact"]}
    search_fields = ["teacher__user__first_name", "teacher__user__last_name", "teacher__user__email", "title"]

    def get_serializer_class(self):
        if self.action == "book":
            return ConsultationBookSerializer
        return ConsultationSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "calendar"):
            return [permissions.AllowAny()]
        if self.action == "book":
            return [permissions.IsAuthenticated()]
        if self.action is None:
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]

    @extend_schema(
        request=inline_serializer(
            name="ConsultationBookRequest",
            fields={"timeslot_ids": drf_serializers.ListField(child=drf_serializers.IntegerField())},
        ),
        responses={201: ConsultationPurchaseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="book")
    def book(self, request, pk=None):
        """
        POST /consultations/{id}/book/
        Student selects timeslots and gets a Stripe PaymentIntent back.
        Payment completion is handled by the webhook.
        """
        consultation = self.get_object()

        if not consultation.standard_price or consultation.standard_price <= 0:
            return Response(
                {"error": "This consultation has no price set. Please contact an admin."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ConsultationBookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        timeslot_ids = serializer.validated_data["timeslot_ids"]

        with transaction.atomic():
            # Lock the timeslots to prevent race conditions
            timeslots = (
                AvailableTimeslot.objects.select_for_update()
                .filter(id__in=timeslot_ids, consultation=consultation, is_booked=False)
            )

            if timeslots.count() != len(timeslot_ids):
                return Response(
                    {"error": "One or more timeslots are unavailable or already booked."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            num_sessions = len(timeslot_ids)

            # Find best bundle discount
            best_bundle = (
                Bundle.objects.filter(
                    consultation=consultation, num_sessions__lte=num_sessions
                )
                .order_by("-num_sessions")
                .first()
            )

            total_price = consultation.standard_price * num_sessions
            if best_bundle:
                discount = best_bundle.discount_percentage / 100
                total_price = round(total_price * (1 - discount), 2)

            # Create a pending purchase — slots NOT marked booked yet (done on webhook)
            purchase = ConsultationPurchase.objects.create(
                student=request.user,
                consultation=consultation,
                bundle_applied=best_bundle,
                total_price_paid=total_price,
                sessions_purchased=num_sessions,
                status="pending",
            )
            purchase.booked_slots.set(timeslots)

        # Create Stripe Checkout Session outside the transaction lock
        session = create_checkout_session(
            line_items=[
                {
                    "price_data": {
                        "currency": settings.CURRENCY,
                        "unit_amount": int(total_price * 100),
                        "product_data": {"name": consultation.title},
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{settings.FRONTEND_URL}/consultation-complete?purchase_id={purchase.id}",
            cancel_url=f"{settings.FRONTEND_URL}/consultations?cancelled=true",
            metadata={
                "purchase_type": "consultation",
                "consultation_purchase_id": purchase.id,
                "user_id": request.user.id,
            },
        )

        purchase.payment_reference = session["id"]
        purchase.save(update_fields=["payment_reference"])

        return Response(
            {
                "purchase_id": purchase.id,
                "checkout_url": session["url"],
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="month",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Month to fetch availability for, in YYYY-MM format (e.g. 2026-04).",
            )
        ]
    )
    @action(detail=True, methods=["get"], url_path="calendar", permission_classes=[permissions.AllowAny])
    def calendar(self, request, pk=None):
        """
        GET /consultations/{id}/calendar/?month=2026-04
        Returns each day of the requested month with its timeslots and availability status.
        Status per day:
          - available:    at least one slot is not booked
          - fully_booked: all slots are booked
        Days with no slots are omitted.
        """
        consultation = self.get_object()
        month_str = request.query_params.get("month")

        if not month_str:
            return Response(
                {"error": "Provide ?month=YYYY-MM"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            year, month = map(int, month_str.split("-"))
        except (ValueError, AttributeError):
            return Response(
                {"error": "Invalid month format. Use YYYY-MM"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        slots = (
            AvailableTimeslot.objects
            .filter(
                consultation=consultation,
                scheduled_start__year=year,
                scheduled_start__month=month,
            )
            .order_by("scheduled_start")
        )

        calendar_data = {}
        for slot in slots:
            day_str = slot.scheduled_start.date().isoformat()
            if day_str not in calendar_data:
                calendar_data[day_str] = {"status": None, "booked": 0, "total": 0}
            calendar_data[day_str]["total"] += 1
            if slot.is_booked:
                calendar_data[day_str]["booked"] += 1

        for day_data in calendar_data.values():
            day_data["status"] = (
                "fully_booked" if day_data["booked"] == day_data["total"] else "available"
            )
            del day_data["booked"]
            del day_data["total"]

        return Response(calendar_data)


class RecurringAvailabilityViewSet(viewsets.ModelViewSet):
    """
    Admin-only. Manage recurring availability rules for a consultation.
    Creating/updating a rule auto-generates AvailableTimeslot rows for 8 weeks.
    """
    serializer_class = RecurringAvailabilitySerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        queryset = RecurringAvailability.objects.all()
        if "consultation_pk" in self.kwargs:
            queryset = queryset.filter(consultation_id=self.kwargs["consultation_pk"])
        return queryset

    def perform_create(self, serializer):
        if "consultation_pk" in self.kwargs:
            serializer.save(consultation_id=self.kwargs["consultation_pk"])
        else:
            serializer.save()


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter timeslots by a specific day (YYYY-MM-DD).",
            )
        ]
    )
)
class AvailableTimeslotViewSet(viewsets.ModelViewSet):
    serializer_class = AvailableTimeslotSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [IsAdminRole()]

    def get_serializer_class(self):
        user = getattr(self.request, "user", None)
        is_admin = user and (user.is_staff or getattr(user, "role", None) == "admin")
        if self.action in ("list", "retrieve") and not is_admin:
            return TimeslotSlimSerializer
        return AvailableTimeslotSerializer

    def get_queryset(self):
        queryset = AvailableTimeslot.objects.all()
        if "consultation_pk" in self.kwargs:
            queryset = queryset.filter(consultation_id=self.kwargs["consultation_pk"])
        date = self.request.query_params.get("date")
        if date:
            queryset = queryset.filter(scheduled_start__date=date)
        return queryset.order_by("scheduled_start")

    def perform_create(self, serializer):
        if "consultation_pk" in self.kwargs:
            serializer.save(consultation_id=self.kwargs["consultation_pk"])
        else:
            serializer.save()


class BundleViewSet(viewsets.ModelViewSet):
    serializer_class = ConsultationBundleSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        queryset = Bundle.objects.all()
        if "consultation_pk" in self.kwargs:
            queryset = queryset.filter(consultation_id=self.kwargs["consultation_pk"])
        return queryset

    def perform_create(self, serializer):
        if "consultation_pk" in self.kwargs:
            serializer.save(consultation_id=self.kwargs["consultation_pk"])
        else:
            serializer.save()


class ConsultationPurchaseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ConsultationPurchaseSerializer

    def get_permissions(self):
        if self.action == "reschedule":
            return [IsAdminRole()]
        if getattr(self.request.user, "role", None) == "admin":
            return [IsAdminRole()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or getattr(user, "role", None) == "admin":
            return ConsultationPurchase.objects.select_related(
                "student", "consultation", "bundle_applied"
            ).prefetch_related("booked_slots").all()
        return ConsultationPurchase.objects.filter(student=user).select_related(
            "consultation", "bundle_applied"
        ).prefetch_related("booked_slots")

    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request, pk=None):
        """
        POST /consultation-purchases/{id}/reschedule/
        Admin only. Move one booked slot to a new available slot.
        Body: { "old_slot_id": <int>, "new_slot_id": <int> }
        """
        purchase = self.get_object()

        old_slot_id = request.data.get("old_slot_id")
        new_slot_id = request.data.get("new_slot_id")

        if not old_slot_id or not new_slot_id:
            return Response(
                {"error": "Both old_slot_id and new_slot_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            old_slot = purchase.booked_slots.get(id=old_slot_id)
        except AvailableTimeslot.DoesNotExist:
            return Response(
                {"error": "old_slot_id is not part of this purchase."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            new_slot = AvailableTimeslot.objects.get(
                id=new_slot_id,
                consultation=purchase.consultation,
                is_booked=False,
            )
        except AvailableTimeslot.DoesNotExist:
            return Response(
                {"error": "new_slot_id is unavailable or does not belong to the same consultation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Cancel old Zoom meeting if one exists
        if old_slot.zoom_meeting_id:
            try:
                from config.zoom import delete_meeting
                delete_meeting(old_slot.zoom_meeting_id)
            except Exception as e:
                logger.warning(f"Failed to delete Zoom meeting {old_slot.zoom_meeting_id}: {e}")

        # Unbook old slot
        old_slot.is_booked = False
        old_slot.zoom_meeting_id = None
        old_slot.zoom_join_url = None
        old_slot.zoom_start_url = None
        old_slot.save(update_fields=["is_booked", "zoom_meeting_id", "zoom_join_url", "zoom_start_url"])

        # Book new slot
        new_slot.is_booked = True
        new_slot.save(update_fields=["is_booked"])

        # Swap in the purchase
        purchase.booked_slots.remove(old_slot)
        purchase.booked_slots.add(new_slot)

        # Create new Zoom meeting async
        from config.tasks import create_zoom_meeting_for_slot_task
        student_name = purchase.student.get_full_name() or purchase.student.email
        create_zoom_meeting_for_slot_task.delay(
            new_slot.id,
            purchase.consultation.title,
            student_name,
        )

        serializer = self.get_serializer(purchase)
        return Response(serializer.data)



class TeacherConsultationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /teacher/consultations/
    Teacher's upcoming booked consultation slots — so they don't miss a session.
    Returns date, time, zoom join link (for student) and zoom start link (to host).
    """

    permission_classes = [IsTeacherRole]
    serializer_class = AvailableTimeslotSerializer

    def get_queryset(self):
        from django.utils import timezone
        return (
            AvailableTimeslot.objects.filter(
                consultation__teacher__user=self.request.user,
                is_booked=True,
                scheduled_start__gte=timezone.now(),
            )
            .order_by("scheduled_start")
        )
