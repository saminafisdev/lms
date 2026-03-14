from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Course, Scholarship
from .serializers import CourseSerializer, ScholarshipSerializer


class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["category", "status", "teacher"]
    search_fields = ["title", "subtitle", "description"]


class ScholarshipViewSet(viewsets.ModelViewSet):
    queryset = Scholarship.objects.all()
    serializer_class = ScholarshipSerializer
