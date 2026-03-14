from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ConsultationViewSet, BundleViewSet

router = DefaultRouter()
router.register(r"consultations", ConsultationViewSet)
router.register(r"bundles", BundleViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
