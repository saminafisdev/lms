import logging
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from orders.stripe import create_checkout_session
from .models import Donation
from .serializers import DonationCreateSerializer, DonationSerializer

logger = logging.getLogger(__name__)


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
                    "checkout_url": {"type": "string"},
                    "donation_id": {"type": "integer"},
                },
            }
        },
        description="Make a one-time anonymous donation. Returns a Stripe Checkout URL to complete payment.",
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
            session = create_checkout_session(
                line_items=[{
                    "price_data": {
                        "currency": settings.CURRENCY,
                        "unit_amount": int(data["amount"] * 100),
                        "product_data": {"name": "Donation"},
                    },
                    "quantity": 1,
                }],
                success_url=f"{settings.FRONTEND_URL}/donate/thank-you?donation_id={donation.id}",
                cancel_url=f"{settings.FRONTEND_URL}/donate?cancelled=true",
                metadata={
                    "purchase_type": "donation",
                    "donation_id": str(donation.id),
                },
            )
        except Exception as e:
            donation.delete()
            logger.error(f"Stripe error during donation: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        donation.stripe_reference = session["id"]
        donation.save(update_fields=["stripe_reference"])

        return Response(
            {"checkout_url": session["url"], "donation_id": donation.id},
            status=status.HTTP_201_CREATED,
        )

