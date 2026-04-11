from django.urls import include, path
from rest_framework_nested import routers

from courses.urls import router as courses_router
from books.urls import router as books_router
from consultations.urls import router as consultations_router
from .views import ReviewViewSet

# Nest reviews under courses: /courses/{course_pk}/reviews/
course_reviews_router = routers.NestedDefaultRouter(courses_router, r"courses", lookup="course")
course_reviews_router.register(r"reviews", ReviewViewSet, basename="course-reviews")

# Nest reviews under books: /books/{book_pk}/reviews/
book_reviews_router = routers.NestedDefaultRouter(books_router, r"books", lookup="book")
book_reviews_router.register(r"reviews", ReviewViewSet, basename="book-reviews")

# Nest reviews under consultations: /consultations/{consultation_pk}/reviews/
consultation_reviews_router = routers.NestedDefaultRouter(
    consultations_router, r"consultations", lookup="consultation"
)
consultation_reviews_router.register(
    r"reviews", ReviewViewSet, basename="consultation-reviews"
)

urlpatterns = [
    path("", include(course_reviews_router.urls)),
    path("", include(book_reviews_router.urls)),
    path("", include(consultation_reviews_router.urls)),
]
