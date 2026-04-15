from django.urls import path, include
from rest_framework_nested import routers

from courses.urls import router as courses_router
from .views import CourseAnnouncementViewSet, SiteAnnouncementViewSet

# Site-wide announcements (admin CRUD + public active endpoint)
router = routers.DefaultRouter()
router.register(r"announcements/site", SiteAnnouncementViewSet, basename="site-announcement")

# Course announcements nested under /courses/{course_slug}/announcements/
course_announcements_router = routers.NestedDefaultRouter(
    courses_router, r"courses", lookup="course"
)
course_announcements_router.register(
    r"announcements", CourseAnnouncementViewSet, basename="course-announcements"
)

urlpatterns = [
    path("", include(router.urls)),
    path("", include(course_announcements_router.urls)),
]
