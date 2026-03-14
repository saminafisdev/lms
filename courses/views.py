from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
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
    queryset = Course.objects.select_related(
        "category", "teacher", "teacher__user"
    ).prefetch_related(
        "modules__lessons__quiz_details__questions__options",
        "modules__lessons__assignment_details",
    ).all()
    serializer_class = CourseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = CourseFilter
    search_fields = ["title", "subtitle", "description"]


class ScholarshipViewSet(viewsets.ModelViewSet):
    queryset = Scholarship.objects.all()
    serializer_class = ScholarshipSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ModuleViewSet(viewsets.ModelViewSet):
    queryset = Module.objects.select_related("course").all()
    serializer_class = ModuleSerializer


class LessonViewSet(viewsets.ModelViewSet):
    queryset = Lesson.objects.select_related("module", "module__course").all()
    serializer_class = LessonSerializer


class QuizViewSet(viewsets.ModelViewSet):
    queryset = Quiz.objects.select_related("lesson").all()
    serializer_class = QuizSerializer


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.select_related("quiz").all()
    serializer_class = QuestionSerializer


class OptionViewSet(viewsets.ModelViewSet):
    queryset = Option.objects.select_related("question").all()
    serializer_class = OptionSerializer


class AssignmentViewSet(viewsets.ModelViewSet):
    queryset = Assignment.objects.select_related("lesson").all()
    serializer_class = AssignmentSerializer
