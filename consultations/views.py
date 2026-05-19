from django.conf import settings
from django.db import transaction
from django.db.models import Sum
import logging
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    inline_serializer,
    OpenApiParameter,
    OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import (
    permissions,
    serializers as drf_serializers,
    status,
    viewsets,
    filters,
)
from rest_framework.decorators import action
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from config.permissions import IsAdminRole, IsTeacherRole
from orders.stripe import create_checkout_session

from .models import (
    AvailableTimeslot,
    Bundle,
    Consultation,
    ConsultationPurchase,
    RecurringAvailability,
    RescheduleRequest,
)
from .serializers import (
    AvailableTimeslotSerializer,
    ConsultationBookSerializer,
    ConsultationBundleSerializer,
    ConsultationPurchaseSerializer,
    ConsultationSerializer,
    RecurringAvailabilitySerializer,
    RescheduleRequestSerializer,
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
    filterset_fields = {
        "teacher": ["exact"],
        "teacher__user__email": ["icontains", "exact"],
    }
    search_fields = [
        "teacher__user__first_name",
        "teacher__user__last_name",
        "teacher__user__email",
        "title",
    ]

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
            fields={
                "timeslot_ids": drf_serializers.ListField(
                    child=drf_serializers.IntegerField()
                )
            },
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
                {
                    "error": "This consultation has no price set. Please contact an admin."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ConsultationBookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        timeslot_ids = serializer.validated_data["timeslot_ids"]

        with transaction.atomic():
            # Lock the timeslots to prevent race conditions
            timeslots = AvailableTimeslot.objects.select_for_update().filter(
                id__in=timeslot_ids, consultation=consultation, is_booked=False
            )

            if timeslots.count() != len(timeslot_ids):
                return Response(
                    {
                        "error": "One or more timeslots are unavailable or already booked."
                    },
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
    @action(
        detail=True,
        methods=["get"],
        url_path="calendar",
        permission_classes=[permissions.AllowAny],
    )
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

        slots = AvailableTimeslot.objects.filter(
            consultation=consultation,
            scheduled_start__year=year,
            scheduled_start__month=month,
        ).order_by("scheduled_start")

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
                "fully_booked"
                if day_data["booked"] == day_data["total"]
                else "available"
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
            rule = serializer.save(consultation_id=self.kwargs["consultation_pk"])
        else:
            rule = serializer.save()
        self._generate_timeslots(rule)

    def perform_update(self, serializer):
        rule = serializer.save()
        from django.utils import timezone

        AvailableTimeslot.objects.filter(
            recurring_rule=rule,
            is_booked=False,
            scheduled_start__gte=timezone.now(),
        ).delete()
        self._generate_timeslots(rule)

    def _generate_timeslots(self, rule):
        from datetime import date, datetime, timedelta
        from django.utils import timezone

        today = date.today()
        start_date = max(rule.valid_from, today)
        end_date = rule.valid_until or (today + timedelta(weeks=8))

        slots_to_create = []
        current = start_date
        while current <= end_date:
            if current.weekday() == rule.weekday:
                slot_start = timezone.make_aware(
                    datetime.combine(current, rule.start_time)
                )
                slot_end = timezone.make_aware(datetime.combine(current, rule.end_time))
                if not AvailableTimeslot.objects.filter(
                    consultation=rule.consultation,
                    scheduled_start=slot_start,
                ).exists():
                    slots_to_create.append(
                        AvailableTimeslot(
                            consultation=rule.consultation,
                            scheduled_start=slot_start,
                            scheduled_end=slot_end,
                            recurring_rule=rule,
                        )
                    )
            current += timedelta(days=1)

        AvailableTimeslot.objects.bulk_create(slots_to_create)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter timeslots by a specific day (YYYY-MM-DD).",
            ),
            OpenApiParameter(
                name="is_booked",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by booking status. `true` = booked slots only, `false` = available slots only.",
            ),
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
        is_booked = self.request.query_params.get("is_booked")
        if is_booked is not None:
            queryset = queryset.filter(is_booked=is_booked.lower() == "true")
        return queryset.order_by("scheduled_start")

    def perform_create(self, serializer):
        if "consultation_pk" in self.kwargs:
            serializer.save(consultation_id=self.kwargs["consultation_pk"])
        else:
            serializer.save()


class BundleViewSet(viewsets.ModelViewSet):
    serializer_class = ConsultationBundleSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]

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
            return (
                ConsultationPurchase.objects.select_related(
                    "student", "consultation", "bundle_applied"
                )
                .prefetch_related("booked_slots")
                .all()
            )
        return (
            ConsultationPurchase.objects.filter(student=user)
            .select_related("consultation", "bundle_applied")
            .prefetch_related("booked_slots")
        )

    @extend_schema(
        summary="Request a reschedule",
        description=(
            "Student submits a reschedule request for one of their booked slots.\n\n"
            "- `old_slot_id`: the currently booked slot to move away from (must belong to this purchase).\n"
            "- `new_slot_id`: the desired new slot (must be unbooked and in the same consultation).\n"
            "- `reason`: optional free-text reason.\n\n"
            "Only one pending reschedule request per slot is allowed at a time. "
            "Cancel the existing request before submitting a new one."
        ),
        request=inline_serializer(
            name="RescheduleRequestInput",
            fields={
                "old_slot_id": drf_serializers.IntegerField(),
                "new_slot_id": drf_serializers.IntegerField(),
                "reason": drf_serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={
            201: RescheduleRequestSerializer,
            400: OpenApiResponse(
                description="Validation error (missing fields, slot not part of purchase, slot unavailable, or duplicate pending request).",
                response=inline_serializer(
                    "RequestRescheduleError400",
                    fields={"error": drf_serializers.CharField()},
                ),
            ),
        },
        tags=["Consultations"],
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="request-reschedule",
        permission_classes=[permissions.IsAuthenticated],
    )
    def request_reschedule(self, request, pk=None):
        purchase = self.get_object()

        if purchase.student != request.user:
            return Response(
                {"error": "You can only request reschedules for your own purchases."},
                status=status.HTTP_403_FORBIDDEN,
            )

        old_slot_id = request.data.get("old_slot_id")
        new_slot_id = request.data.get("new_slot_id")
        reason = request.data.get("reason", "")

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
                {
                    "error": "new_slot_id is unavailable or does not belong to the same consultation."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if RescheduleRequest.objects.filter(
            old_slot=old_slot, status=RescheduleRequest.STATUS_PENDING
        ).exists():
            return Response(
                {
                    "error": "A pending reschedule request for this slot already exists. Cancel it before submitting a new one."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        rr = RescheduleRequest.objects.create(
            purchase=purchase,
            old_slot=old_slot,
            requested_slot=new_slot,
            reason=reason,
        )
        return Response(
            RescheduleRequestSerializer(rr).data, status=status.HTTP_201_CREATED
        )


def _perform_slot_swap(purchase, old_slot, new_slot):
    """Swap slots on a purchase and fire Zoom creation task."""
    if old_slot.zoom_meeting_id:
        try:
            from config.zoom import delete_meeting

            delete_meeting(old_slot.zoom_meeting_id)
        except Exception as e:
            logger.warning(
                f"Failed to delete Zoom meeting {old_slot.zoom_meeting_id}: {e}"
            )

    old_slot.is_booked = False
    old_slot.zoom_meeting_id = None
    old_slot.zoom_join_url = None
    old_slot.zoom_start_url = None
    old_slot.save(
        update_fields=[
            "is_booked",
            "zoom_meeting_id",
            "zoom_join_url",
            "zoom_start_url",
        ]
    )

    new_slot.is_booked = True
    new_slot.save(update_fields=["is_booked"])

    purchase.booked_slots.remove(old_slot)
    purchase.booked_slots.add(new_slot)

    from config.tasks import create_zoom_meeting_for_slot_task

    student_name = purchase.student.get_full_name() or purchase.student.email
    create_zoom_meeting_for_slot_task.delay(
        new_slot.id, purchase.consultation.title, student_name
    )


@extend_schema_view(
    list=extend_schema(summary="List reschedule requests", tags=["Consultations"]),
    retrieve=extend_schema(
        summary="Retrieve a reschedule request", tags=["Consultations"]
    ),
)
class RescheduleRequestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RescheduleRequestSerializer

    def get_permissions(self):
        if self.action in ("accept", "decline"):
            return [IsAdminRole()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or getattr(user, "role", None) == "admin":
            qs = RescheduleRequest.objects.select_related(
                "purchase__student", "old_slot", "requested_slot"
            ).all()
        else:
            qs = RescheduleRequest.objects.filter(
                purchase__student=user
            ).select_related("purchase", "old_slot", "requested_slot")

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @extend_schema(
        summary="Cancel a reschedule request",
        description="Student cancels their own pending reschedule request.",
        request=None,
        responses={
            200: RescheduleRequestSerializer,
            400: OpenApiResponse(
                description="Request is not pending.",
                response=inline_serializer(
                    "CancelError400", fields={"error": drf_serializers.CharField()}
                ),
            ),
            403: OpenApiResponse(
                description="Not your request.",
                response=inline_serializer(
                    "CancelError403", fields={"error": drf_serializers.CharField()}
                ),
            ),
        },
        tags=["Consultations"],
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="cancel",
        permission_classes=[permissions.IsAuthenticated],
    )
    def cancel(self, request, pk=None):
        rr = self.get_object()
        if rr.purchase.student != request.user:
            return Response(
                {"error": "You can only cancel your own reschedule requests."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if rr.status != RescheduleRequest.STATUS_PENDING:
            return Response(
                {"error": "Only pending requests can be cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rr.status = RescheduleRequest.STATUS_CANCELLED
        rr.save(update_fields=["status", "updated_at"])
        return Response(RescheduleRequestSerializer(rr).data)

    @extend_schema(
        summary="Accept a reschedule request",
        description=(
            "Admin accepts the student's reschedule request.\n\n"
            "- Performs the slot swap.\n"
            "- Fires Zoom meeting creation for the new slot.\n"
            "- Sends the student an email notification.\n\n"
            "**Permissions:** Admin only.\n\n"
            "**400 cases:**\n"
            '- `"Only pending requests can be accepted."` — request is already accepted/declined/cancelled.\n'
            '- `"The requested slot is no longer available."` — another booking took the slot between the request and acceptance.'
        ),
        request=None,
        responses={
            200: RescheduleRequestSerializer,
            400: OpenApiResponse(
                description="Request is not pending, or the requested slot was booked by someone else.",
                response=inline_serializer(
                    "AcceptError400", fields={"error": drf_serializers.CharField()}
                ),
            ),
        },
        tags=["Consultations"],
    )
    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, pk=None):
        rr = self.get_object()
        if rr.status != RescheduleRequest.STATUS_PENDING:
            return Response(
                {"error": "Only pending requests can be accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Re-check the requested slot is still free
        new_slot = rr.requested_slot
        if new_slot.is_booked:
            return Response(
                {"error": "The requested slot is no longer available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            _perform_slot_swap(rr.purchase, rr.old_slot, new_slot)
            rr.status = RescheduleRequest.STATUS_ACCEPTED
            rr.save(update_fields=["status", "updated_at"])

        student = rr.purchase.student
        try:
            from email_templates.sendgrid import send_email

            send_email(
                to_email=student.email,
                purpose="consultation_reschedule_accepted",
                template_data={
                    "first_name": student.first_name or student.email,
                    "old_slot_time": str(rr.old_slot.scheduled_start),
                    "new_slot_time": str(new_slot.scheduled_start),
                },
            )
        except Exception as e:
            logger.warning(
                f"Failed to send reschedule accepted email to {student.email}: {e}"
            )

        return Response(RescheduleRequestSerializer(rr).data)

    @extend_schema(
        summary="Decline a reschedule request",
        description=(
            "Admin declines the student's reschedule request. No slot swap occurs.\n\n"
            "The student is notified by email.\n\n"
            "**Permissions:** Admin only."
        ),
        request=None,
        responses={
            200: RescheduleRequestSerializer,
            400: OpenApiResponse(
                description="Request is not pending.",
                response=inline_serializer(
                    "DeclineError400", fields={"error": drf_serializers.CharField()}
                ),
            ),
        },
        tags=["Consultations"],
    )
    @action(detail=True, methods=["post"], url_path="decline")
    def decline(self, request, pk=None):
        rr = self.get_object()
        if rr.status != RescheduleRequest.STATUS_PENDING:
            return Response(
                {"error": "Only pending requests can be declined."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rr.status = RescheduleRequest.STATUS_DECLINED
        rr.save(update_fields=["status", "updated_at"])

        student = rr.purchase.student
        try:
            from email_templates.sendgrid import send_email

            send_email(
                to_email=student.email,
                purpose="consultation_reschedule_declined",
                template_data={
                    "first_name": student.first_name or student.email,
                    "old_slot_time": str(rr.old_slot.scheduled_start),
                },
            )
        except Exception as e:
            logger.warning(
                f"Failed to send reschedule declined email to {student.email}: {e}"
            )

        return Response(RescheduleRequestSerializer(rr).data)


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

        return AvailableTimeslot.objects.filter(
            consultation__teacher__user=self.request.user,
            is_booked=True,
            scheduled_start__gte=timezone.now(),
        ).order_by("scheduled_start")

    @extend_schema(
        summary="Get current month's consultation earnings",
        responses={
            200: inline_serializer(
                name="TeacherConsultationEarningsResponse",
                fields={
                    "month": drf_serializers.CharField(),
                    "sessions": drf_serializers.IntegerField(),
                    "consultation_rate": drf_serializers.FloatField(),
                    "earnings": drf_serializers.FloatField(),
                },
            )
        },
    )
    @action(detail=False, methods=["get"], url_path="consultation-earnings")
    def consultation_earnings(self, request):
        """
        Returns the current month's consultation earnings for the authenticated teacher.
        """
        from django.utils import timezone

        user = request.user
        teacher_profile = getattr(user, "teacher_profile", None)
        if not teacher_profile:
            return Response({"error": "No teacher profile found."}, status=400)
        now = timezone.now()
        first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        purchases = ConsultationPurchase.objects.filter(
            consultation__teacher=teacher_profile,
            status="completed",
            created_at__gte=first_of_month,
            created_at__lte=now,
        )
        total_sessions = (
            purchases.aggregate(Sum("sessions_purchased"))["sessions_purchased__sum"]
            or 0
        )
        earnings = float(teacher_profile.consultation_rate) * total_sessions
        return Response(
            {
                "month": now.strftime("%Y-%m"),
                "sessions": total_sessions,
                "consultation_rate": float(teacher_profile.consultation_rate),
                "earnings": earnings,
            }
        )
