from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CourseViewSet, ScholarshipViewSet

router = DefaultRouter()
router.register(r"courses", CourseViewSet)
router.register(r"scholarships", ScholarshipViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
