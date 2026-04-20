from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TeacherProfileViewSet,
    StudentProfileViewSet,
    StudentDashboardView,
    AdminDashboardView,
    NewsletterSubscribeView,
    NewsletterUnsubscribeView,
    NewsletterSubscriberViewSet,
)

router = DefaultRouter()
router.register(r"teacher-profiles", TeacherProfileViewSet)
router.register(r"student-profiles", StudentProfileViewSet)
router.register(r"newsletter/subscribers", NewsletterSubscriberViewSet, basename="newsletter-subscribers")

urlpatterns = [
    path("", include(router.urls)),
    path("student/dashboard/", StudentDashboardView.as_view(), name="student-dashboard"),
    path("dashboard/admin/", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("newsletter/subscribe/", NewsletterSubscribeView.as_view(), name="newsletter-subscribe"),
    path("newsletter/unsubscribe/", NewsletterUnsubscribeView.as_view(), name="newsletter-unsubscribe"),
]
