from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TeacherProfileViewSet, StudentProfileViewSet, StudentDashboardView

router = DefaultRouter()
router.register(r"teacher-profiles", TeacherProfileViewSet)
router.register(r"student-profiles", StudentProfileViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("student/dashboard/", StudentDashboardView.as_view(), name="student-dashboard"),
]
