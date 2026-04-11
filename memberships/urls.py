from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MembershipPlanViewSet, UserMembershipAdminViewSet

router = DefaultRouter()
router.register("membership", MembershipPlanViewSet, basename="membership")
router.register("membership/members", UserMembershipAdminViewSet, basename="membership-members")

urlpatterns = [
    path("", include(router.urls)),
]
