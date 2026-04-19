from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import permissions, serializers as drf_serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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

    def get_serializer_class(self):
        if self.action == "book":
            return ConsultationBookSerializer
        return ConsultationSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "book", "calendar"):
            return [permissions.IsAuthenticated()]
        if self.action is None:
            # Unrecognised method (e.g. GET on a POST-only action) — let DRF return 405
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
    @action(detail=True, methods=["get"], url_path="calendar", permission_classes=[permissions.IsAuthenticated])
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
            .filter(consultation=consultation, day__year=year, day__month=month)
            .order_by("day", "start_time")
        )

        calendar_data = {}
        for slot in slots:
            day_str = slot.day.isoformat()
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
            return [permissions.IsAuthenticated()]
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
            queryset = queryset.filter(day=date)
        return queryset.order_by("start_time")

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
        today = timezone.now().date()
        return (
            AvailableTimeslot.objects.filter(
                consultation__teacher__user=self.request.user,
                is_booked=True,
                day__gte=today,
            )
            .order_by("day", "start_time")
        )
