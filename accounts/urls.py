from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TeacherProfileViewSet, StudentProfileViewSet

router = DefaultRouter()
router.register(r"teacher-profiles", TeacherProfileViewSet)
router.register(r"student-profiles", StudentProfileViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
