from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import TeacherProfile, StudentProfile
from .serializers import (
    StudentProfileSerializer,
    TeacherProfileSerializer,
)


class TeacherProfileViewSet(viewsets.ModelViewSet):
    queryset = TeacherProfile.objects.all()
    serializer_class = TeacherProfileSerializer
    # permission_classes = [IsAuthenticated]


class StudentProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.all()
    serializer_class = StudentProfileSerializer
    # permission_classes = [IsAuthenticated]
