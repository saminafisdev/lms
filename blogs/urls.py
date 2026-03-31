from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BlogViewSet, BlogCategoryViewSet

router = DefaultRouter()
router.register(r"categories", BlogCategoryViewSet, basename="blog-category")
router.register(r"", BlogViewSet, basename="blog")

urlpatterns = [
    path("", include(router.urls)),
]