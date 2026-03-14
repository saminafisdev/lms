from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CourseViewSet,
    ScholarshipViewSet,
    CategoryViewSet,
    ModuleViewSet,
    LessonViewSet,
    QuizViewSet,
    QuestionViewSet,
    OptionViewSet,
    AssignmentViewSet,
)

router = DefaultRouter()
router.register(r"courses", CourseViewSet)
router.register(r"scholarships", ScholarshipViewSet)
router.register(r"categories", CategoryViewSet)
router.register(r"modules", ModuleViewSet)
router.register(r"lessons", LessonViewSet)
router.register(r"quizzes", QuizViewSet)
router.register(r"questions", QuestionViewSet)
router.register(r"options", OptionViewSet)
router.register(r"assignments", AssignmentViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
