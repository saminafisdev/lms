from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DoorViewSet

router = DefaultRouter()
router.register(r"doors", DoorViewSet, basename="door")

urlpatterns = [
    path("", include(router.urls)),
]
