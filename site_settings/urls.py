from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import site_settings_detail, site_settings_update, TestimonialViewSet

router = DefaultRouter()
router.register("testimonials", TestimonialViewSet, basename="testimonial")

urlpatterns = [
    path("site-settings/", site_settings_detail, name="site-settings-detail"),
    path("site-settings/update/", site_settings_update, name="site-settings-update"),
    path("", include(router.urls)),
]
