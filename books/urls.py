from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BookViewSet, BookCategoryViewSet, BookGalleryImageViewSet

router = DefaultRouter()
router.register(r"books", BookViewSet, basename="book")
router.register(r"book-categories", BookCategoryViewSet, basename="book-category")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "books/<slug:book_slug>/gallery/",
        BookGalleryImageViewSet.as_view({'get': 'list', 'post': 'create'}),
        name="book-gallery-list"
    ),
    path(
        "books/<slug:book_slug>/gallery/<int:pk>/",
        BookGalleryImageViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}),
        name="book-gallery-detail"
    ),
]
