from django.urls import path, include
from rest_framework_nested import routers
from .views import (
    CourseViewSet,
    BundleViewSet,
    ScholarshipViewSet,
    CourseCategoryViewSet,
    ModuleViewSet,
    LessonViewSet,
    QuizViewSet,
    QuestionViewSet,
    OptionViewSet,
    AssignmentViewSet,
    AssignmentSubmissionViewSet,
    EnrollmentViewSet,
    TeacherLiveSessionViewSet,
    TeacherDashboardView,
)

router = routers.DefaultRouter()
router.register(r"courses", CourseViewSet, basename="course")
router.register(r"bundles", BundleViewSet, basename="bundle")
router.register(r"scholarships", ScholarshipViewSet, basename="scholarship")
router.register(r"course-categories", CourseCategoryViewSet)
router.register(r"enrollments", EnrollmentViewSet, basename="enrollment")
router.register(r"assignment-submissions", AssignmentSubmissionViewSet, basename="assignment-submission")

course_router = routers.NestedDefaultRouter(router, r"courses", lookup="course")
course_router.register(r"modules", ModuleViewSet, basename="course-modules")

module_router = routers.NestedDefaultRouter(course_router, r"modules", lookup="module")
module_router.register(r"lessons", LessonViewSet, basename="module-lessons")

lesson_router = routers.NestedDefaultRouter(module_router, r"lessons", lookup="lesson")
lesson_router.register(r"quizzes", QuizViewSet, basename="lesson-quizzes")
lesson_router.register(r"assignments", AssignmentViewSet, basename="lesson-assignments")

quiz_router = routers.NestedDefaultRouter(lesson_router, r"quizzes", lookup="quiz")
quiz_router.register(r"questions", QuestionViewSet, basename="quiz-questions")

question_router = routers.NestedDefaultRouter(
    quiz_router, r"questions", lookup="question"
)
question_router.register(r"options", OptionViewSet, basename="question-options")

teacher_router = routers.DefaultRouter()
teacher_router.register(r"live-sessions", TeacherLiveSessionViewSet, basename="teacher-live-sessions")
teacher_router.register(r"dashboard", TeacherDashboardView, basename="teacher-dashboard")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(course_router.urls)),
    path("", include(module_router.urls)),
    path("", include(lesson_router.urls)),
    path("", include(quiz_router.urls)),
    path("", include(question_router.urls)),
    path("teacher/", include(teacher_router.urls)),
]
