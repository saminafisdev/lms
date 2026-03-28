from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Prefetch
import django_filters
from accounts.models import TeacherProfile
from .models import (
    Course,
    Scholarship,
    Category,
    Module,
    Lesson,
    Quiz,
    Question,
    Option,
    Assignment,
)
from .serializers import (
    CourseSerializer,
    ScholarshipSerializer,
    CategorySerializer,
    ModuleSerializer,
    LessonSerializer,
    QuizSerializer,
    QuestionSerializer,
    OptionSerializer,
    AssignmentSerializer,
)


class CourseFilter(django_filters.FilterSet):
    teacher = django_filters.ModelChoiceFilter(
        queryset=TeacherProfile.objects.select_related("user").all()
    )

    class Meta:
        model = Course
        fields = ["category", "status", "teacher"]


class CourseViewSet(viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = CourseFilter
    search_fields = ["title", "subtitle", "description"]

    def get_queryset(self):
        base_qs = (
            Course.objects.select_related("category", "teacher", "teacher__user")
            .prefetch_related(
                Prefetch("modules", queryset=Module.objects.order_by("order")),
                Prefetch("modules__lessons", queryset=Lesson.objects.order_by("order")),
                "modules__lessons__quiz_details__questions__options",
                "modules__lessons__assignment_details",
            )
        )

        user = self.request.user

        if not user.is_authenticated:
            # Unauthenticated users see only active courses
            return base_qs.filter(is_active=True)

        role = getattr(user, "role", None)

        if role == "admin" or user.is_staff:
            return base_qs.all()

        if role == "teacher":
            return base_qs.filter(teacher__user=user)

        # Students (and any other role) see only active courses
        return base_qs.filter(is_active=True)


class ScholarshipViewSet(viewsets.ModelViewSet):
    queryset = Scholarship.objects.all()
    serializer_class = ScholarshipSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ModuleViewSet(viewsets.ModelViewSet):
    serializer_class = ModuleSerializer

    def get_queryset(self):
        queryset = Module.objects.select_related("course").order_by("order").all()
        if "course_pk" in self.kwargs:
            queryset = queryset.filter(course_id=self.kwargs["course_pk"])
        return queryset

    def perform_create(self, serializer):
        if "course_pk" in self.kwargs:
            serializer.save(course_id=self.kwargs["course_pk"])
        else:
            serializer.save()


class LessonViewSet(viewsets.ModelViewSet):
    serializer_class = LessonSerializer

    def get_queryset(self):
        queryset = (
            Lesson.objects.select_related("module", "module__course")
            .order_by("order")
            .all()
        )
        if "module_pk" in self.kwargs:
            queryset = queryset.filter(module_id=self.kwargs["module_pk"])
        return queryset

    def perform_create(self, serializer):
        if "module_pk" in self.kwargs:
            serializer.save(module_id=self.kwargs["module_pk"])
        else:
            serializer.save()


class QuizViewSet(viewsets.ModelViewSet):
    serializer_class = QuizSerializer

    def get_queryset(self):
        queryset = Quiz.objects.select_related("lesson").all()
        if "lesson_pk" in self.kwargs:
            queryset = queryset.filter(lesson_id=self.kwargs["lesson_pk"])
        return queryset

    def perform_create(self, serializer):
        if "lesson_pk" in self.kwargs:
            serializer.save(lesson_id=self.kwargs["lesson_pk"])
        else:
            serializer.save()


class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer

    def get_queryset(self):
        queryset = Question.objects.select_related("quiz").all()
        if "quiz_pk" in self.kwargs:
            queryset = queryset.filter(quiz_id=self.kwargs["quiz_pk"])
        return queryset

    def perform_create(self, serializer):
        if "quiz_pk" in self.kwargs:
            serializer.save(quiz_id=self.kwargs["quiz_pk"])
        else:
            serializer.save()


class OptionViewSet(viewsets.ModelViewSet):
    serializer_class = OptionSerializer

    def get_queryset(self):
        queryset = Option.objects.select_related("question").all()
        if "question_pk" in self.kwargs:
            queryset = queryset.filter(question_id=self.kwargs["question_pk"])
        return queryset

    def perform_create(self, serializer):
        if "question_pk" in self.kwargs:
            serializer.save(question_id=self.kwargs["question_pk"])
        else:
            serializer.save()


class AssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        queryset = Assignment.objects.select_related("lesson").all()
        if "lesson_pk" in self.kwargs:
            queryset = queryset.filter(lesson_id=self.kwargs["lesson_pk"])
        return queryset

    def perform_create(self, serializer):
        if "lesson_pk" in self.kwargs:
            serializer.save(lesson_id=self.kwargs["lesson_pk"])
        else:
            serializer.save()
