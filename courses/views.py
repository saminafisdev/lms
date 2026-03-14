from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
import django_filters
from accounts.models import TeacherProfile
from .models import Course, Scholarship
from .serializers import CourseSerializer, ScholarshipSerializer


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
    ).all()
    serializer_class = CourseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = CourseFilter
    search_fields = ["title", "subtitle", "description"]


class ScholarshipViewSet(viewsets.ModelViewSet):
    queryset = Scholarship.objects.all()
    serializer_class = ScholarshipSerializer
