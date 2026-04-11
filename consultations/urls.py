from django.urls import path, include
from rest_framework_nested import routers
from .views import (
    ConsultationViewSet,
    AvailableTimeslotViewSet,
    BundleViewSet,
    ConsultationPurchaseViewSet,
)

router = routers.DefaultRouter()
router.register(r"consultations", ConsultationViewSet)
router.register(r"purchases", ConsultationPurchaseViewSet, basename="consultation-purchase")

consultation_router = routers.NestedDefaultRouter(router, r"consultations", lookup="consultation")
consultation_router.register(r"timeslots", AvailableTimeslotViewSet, basename="consultation-timeslots")
consultation_router.register(r"bundles", BundleViewSet, basename="consultation-bundles")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(consultation_router.urls)),
]
