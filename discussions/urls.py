from rest_framework_nested import routers
from django.urls import path, include
from .views import PostViewSet, ReplyViewSet
from courses.urls import router as courses_router

discussions_router = routers.NestedDefaultRouter(courses_router, r"courses", lookup="course")
discussions_router.register(r"discussions", PostViewSet, basename="course-discussions")

replies_router = routers.NestedDefaultRouter(discussions_router, r"discussions", lookup="post")
replies_router.register(r"replies", ReplyViewSet, basename="discussion-replies")

urlpatterns = [
    path("", include(discussions_router.urls)),
    path("", include(replies_router.urls)),
]
