from django.urls import path, include
from rest_framework_nested import routers
from .views import (
    ConsultationViewSet,
    AvailableTimeslotViewSet,
    BundleViewSet,
    ConsultationPurchaseViewSet,
    RecurringAvailabilityViewSet,
    TeacherConsultationViewSet,
)

router = routers.DefaultRouter()
router.register(r"consultations", ConsultationViewSet)
router.register(r"purchases", ConsultationPurchaseViewSet, basename="consultation-purchase")

consultation_router = routers.NestedDefaultRouter(router, r"consultations", lookup="consultation")
consultation_router.register(r"timeslots", AvailableTimeslotViewSet, basename="consultation-timeslots")
consultation_router.register(r"bundles", BundleViewSet, basename="consultation-bundles")
consultation_router.register(r"recurring", RecurringAvailabilityViewSet, basename="consultation-recurring")

teacher_router = routers.DefaultRouter()
teacher_router.register(r"consultations", TeacherConsultationViewSet, basename="teacher-consultations")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(consultation_router.urls)),
    path("teacher/", include(teacher_router.urls)),
]
