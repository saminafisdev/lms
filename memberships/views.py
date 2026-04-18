import logging
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, mixins
from orders.stripe import create_checkout_session
from config.permissions import IsAdminRole, IsStudent
from .models import MembershipPlan, UserMembership
from .serializers import MembershipPlanSerializer, UserMembershipSerializer, UserMembershipAdminSerializer

logger = logging.getLogger(__name__)


class MembershipPlanViewSet(viewsets.GenericViewSet):
    serializer_class = MembershipPlanSerializer

    def get_permissions(self):
        if self.action == "retrieve_plan":
            return [AllowAny()]
        if self.action == "subscribe":
            return [IsStudent()]
        if self.action == "my_status":
            return [IsAuthenticated()]
        return [IsAdminUser()]

    @extend_schema(responses=MembershipPlanSerializer, description="Get current membership plan details (public).")
    @action(detail=False, methods=["get"], url_path="plan")
    def retrieve_plan(self, request):
        plan = MembershipPlan.get()
        return Response(MembershipPlanSerializer(plan).data)

    @extend_schema(
        request=MembershipPlanSerializer,
        responses=MembershipPlanSerializer,
        description="Update the membership plan (admin only). All fields optional.",
    )
    @action(detail=False, methods=["patch"], url_path="plan/update")
    def update_plan(self, request):
        plan = MembershipPlan.get()
        serializer = MembershipPlanSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        request=None,
        responses={201: {"type": "object", "properties": {"checkout_url": {"type": "string"}, "membership_id": {"type": "integer"}}}},
        description="Subscribe to the membership plan. No request body needed. Returns a Stripe checkout_url — redirect the user to this URL to complete payment.",
    )
    @action(detail=False, methods=["post"], url_path="subscribe", permission_classes=[IsStudent])
    def subscribe(self, request):
        plan = MembershipPlan.get()
        if not plan.is_active:
            return Response({"error": "Membership is not currently available."}, status=status.HTTP_400_BAD_REQUEST)

        membership, created = UserMembership.objects.get_or_create(
            user=request.user,
            defaults={"plan": plan, "status": UserMembership.Status.PENDING},
        )

        # If already active, return info
        if not created and membership.is_currently_active:
            return Response(
                {"error": "You already have an active membership.", "end_date": membership.end_date},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Reset to pending if re-subscribing
        if not created:
            membership.plan = plan
            membership.status = UserMembership.Status.PENDING
            membership.save(update_fields=["plan", "status", "updated_at"])

        frontend_url = settings.FRONTEND_URL
        session = create_checkout_session(
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": int(plan.price * 100),
                    "product_data": {"name": f"Membership – {plan.name}"},
                },
                "quantity": 1,
            }],
            success_url=f"{frontend_url}/membership/success?membership_id={membership.id}",
            cancel_url=f"{frontend_url}/membership/cancel",
            metadata={
                "purchase_type": "membership",
                "membership_id": str(membership.id),
                "user_id": str(request.user.id),
            },
        )
        membership.payment_reference = session["id"]
        membership.save(update_fields=["payment_reference", "updated_at"])

        return Response(
            {"checkout_url": session["url"], "membership_id": membership.id},
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses=UserMembershipSerializer, description="Get the current user's membership status.")
    @action(detail=False, methods=["get"], url_path="my-status", permission_classes=[IsAuthenticated])
    def my_status(self, request):
        try:
            membership = UserMembership.objects.select_related("plan").get(user=request.user)
        except UserMembership.DoesNotExist:
            return Response({"detail": "No membership found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(UserMembershipSerializer(membership).data)


class UserMembershipAdminViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Admin-only view to manage all user memberships."""
    permission_classes = [IsAdminUser]
    queryset = UserMembership.objects.select_related("user", "plan").all()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return UserMembershipAdminSerializer
        return UserMembershipSerializer

