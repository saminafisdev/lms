from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CertificateViewSet, CertificateTemplateViewSet

router = DefaultRouter()
router.register(
    r"certificate-templates",
    CertificateTemplateViewSet,
    basename="certificate-template",
)
router.register(r"certificates", CertificateViewSet, basename="certificate")

urlpatterns = [
    path("", include(router.urls)),
]
