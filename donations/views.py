import stripe
import logging
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from .models import Donation
from .serializers import DonationCreateSerializer, DonationSerializer

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class DonationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Donation.objects.all()
    permission_classes = [IsAdminUser]
    serializer_class = DonationSerializer

    @extend_schema(
        request=DonationCreateSerializer,
        responses={
            201: {
                "type": "object",
                "properties": {
                    "client_secret": {"type": "string"},
                    "donation_id": {"type": "integer"},
                },
            }
        },
        description="Make a one-time anonymous donation. Returns a Stripe PaymentIntent client_secret to complete payment.",
    )
    @action(detail=False, methods=["post"], permission_classes=[AllowAny], url_path="donate")
    def donate(self, request):
        serializer = DonationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        donation = Donation.objects.create(
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            amount=data["amount"],
            status=Donation.Status.PENDING,
        )

        try:
            intent = stripe.PaymentIntent.create(
                amount=int(data["amount"] * 100),
                currency=settings.CURRENCY,
                receipt_email=data["email"],
                metadata={
                    "purchase_type": "donation",
                    "donation_id": str(donation.id),
                },
                automatic_payment_methods={"enabled": True},
            )
        except stripe.error.StripeError as e:
            donation.delete()
            logger.error(f"Stripe error during donation: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        donation.stripe_reference = intent["id"]
        donation.save(update_fields=["stripe_reference"])

        return Response(
            {"client_secret": intent["client_secret"], "donation_id": donation.id},
            status=status.HTTP_201_CREATED,
        )


