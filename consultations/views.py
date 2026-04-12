from django.conf import settings
from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from config.permissions import IsAdminRole
from orders.stripe import create_payment_intent

from .models import AvailableTimeslot, Bundle, Consultation, ConsultationPurchase, RecurringAvailability
from .serializers import (
    AvailableTimeslotSerializer,
    BundleSerializer,
    ConsultationPurchaseSerializer,
    ConsultationSerializer,
    RecurringAvailabilitySerializer,
)


class ConsultationViewSet(viewsets.ModelViewSet):
    queryset = (
        Consultation.objects.select_related("teacher", "teacher__user")
        .prefetch_related("timeslots", "bundles", "recurring_rules")
        .all()
    )
    serializer_class = ConsultationSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        if self.action == "book":
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]

    @action(detail=True, methods=["post"], url_path="book")
    def book(self, request, pk=None):
        """
        POST /consultations/{id}/book/
        Student selects timeslots and gets a Stripe PaymentIntent back.
        Payment completion is handled by the webhook.
        """
        consultation = self.get_object()

        timeslot_ids = request.data.get("timeslot_ids", [])
        if not timeslot_ids:
            return Response(
                {"error": "No timeslots selected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        # Create Stripe PaymentIntent outside the transaction lock
        intent = create_payment_intent(
            amount=total_price,
            metadata={
                "purchase_type": "consultation",
                "consultation_purchase_id": purchase.id,
                "user_id": request.user.id,
            },
        )

        purchase.payment_reference = intent["id"]
        purchase.save(update_fields=["payment_reference"])

        return Response(
            {
                "purchase": ConsultationPurchaseSerializer(purchase).data,
                "client_secret": intent["client_secret"],
                "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            },
            status=status.HTTP_201_CREATED,
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
                calendar_data[day_str] = {"status": None, "slots": []}
            calendar_data[day_str]["slots"].append({
                "id": slot.id,
                "start_time": slot.start_time.strftime("%H:%M"),
                "end_time": slot.end_time.strftime("%H:%M"),
                "is_booked": slot.is_booked,
            })

        for day_data in calendar_data.values():
            all_booked = all(s["is_booked"] for s in day_data["slots"])
            day_data["status"] = "fully_booked" if all_booked else "available"

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


class AvailableTimeslotViewSet(viewsets.ModelViewSet):
    serializer_class = AvailableTimeslotSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        queryset = AvailableTimeslot.objects.all()
        if "consultation_pk" in self.kwargs:
            queryset = queryset.filter(consultation_id=self.kwargs["consultation_pk"])
        return queryset

    def perform_create(self, serializer):
        if "consultation_pk" in self.kwargs:
            serializer.save(consultation_id=self.kwargs["consultation_pk"])
        else:
            serializer.save()


class BundleViewSet(viewsets.ModelViewSet):
    serializer_class = BundleSerializer
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

