from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BookViewSet, BookCategoryViewSet

router = DefaultRouter()
router.register(r"books", BookViewSet, basename="book")
router.register(r"book-categories", BookCategoryViewSet, basename="book-category")

urlpatterns = [
    path("", include(router.urls)),
]
