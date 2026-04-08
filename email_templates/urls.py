from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmailTemplateConfigViewSet

router = DefaultRouter()
router.register(
    r"email-templates", EmailTemplateConfigViewSet, basename="email-template"
)

urlpatterns = [
    path("", include(router.urls)),
]
