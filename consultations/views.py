from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from .models import Consultation, AvailableTimeslot, Bundle, ConsultationPurchase
from .serializers import (
    ConsultationSerializer,
    AvailableTimeslotSerializer,
    BundleSerializer,
    ConsultationPurchaseSerializer,
)


class ConsultationViewSet(viewsets.ModelViewSet):
    queryset = (
        Consultation.objects.select_related("teacher", "teacher__user")
        .prefetch_related("timeslots", "bundles")
        .all()
    )
    serializer_class = ConsultationSerializer

    @action(detail=True, methods=["post"])
    def book(self, request, pk=None):
        consultation = self.get_object()
        student = request.user

        if not student.is_authenticated:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        timeslot_ids = request.data.get("timeslot_ids", [])
        if not timeslot_ids:
            return Response(
                {"error": "No timeslots selected"}, status=status.HTTP_400_BAD_REQUEST
            )

        timeslots = AvailableTimeslot.objects.filter(
            id__in=timeslot_ids, consultation=consultation, is_booked=False
        )

        if len(timeslots) != len(timeslot_ids):
            return Response(
                {"error": "One or more timeslots are unavailable or invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        num_sessions = len(timeslots)

        # Logic for bundle
        best_bundle = (
            Bundle.objects.filter(
                consultation=consultation, num_sessions__lte=num_sessions
            )
            .order_by("-num_sessions")
            .first()
        )

        standard_price = consultation.standard_price
        total_price = standard_price * num_sessions

        if best_bundle:
            discount = best_bundle.discount_percentage / 100
            total_price = total_price * (1 - discount)


        with transaction.atomic():
            purchase = ConsultationPurchase.objects.create(
                student=student,
                consultation=consultation,
                bundle_applied=best_bundle,
                total_price_paid=total_price,
                sessions_purchased=num_sessions,
            )
            purchase.booked_slots.set(timeslots)

            # Mark timeslots as booked
            timeslots.update(is_booked=True)

        return Response(
            ConsultationPurchaseSerializer(purchase).data,
            status=status.HTTP_201_CREATED,
        )


class AvailableTimeslotViewSet(viewsets.ModelViewSet):
    serializer_class = AvailableTimeslotSerializer

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
    queryset = ConsultationPurchase.objects.all()
    serializer_class = ConsultationPurchaseSerializer

    def get_queryset(self):
        return self.queryset.filter(student=self.request.user)
