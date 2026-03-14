from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ConsultationViewSet,
    AvailableTimeslotViewSet,
    BundleViewSet,
    ConsultationPurchaseViewSet,
)

router = DefaultRouter()
router.register(r"consultations", ConsultationViewSet)
router.register(r"timeslots", AvailableTimeslotViewSet)
router.register(r"bundles", BundleViewSet)
router.register(r"purchases", ConsultationPurchaseViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
