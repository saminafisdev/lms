from courses.models import LessonCompletion
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Prefetch
import django_filters
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view, inline_serializer
from drf_spectacular.openapi import AutoSchema
from rest_framework import fields as drf_fields
from accounts.models import TeacherProfile
from config.permissions import IsAdminRole
from .models import (
    Course,
    Bundle,
    Scholarship,
    CourseCategory,
    Module,
    Lesson,
    Quiz,
    Question,
    Option,
    Assignment,
    Enrollment,
)
from .serializers import (
    CourseSerializer,
    BundleSerializer,
    ScholarshipSerializer,
    ScholarshipDocumentSerializer,
    ApproveScholarshipSerializer,
    RejectScholarshipSerializer,
    CourseCategorySerializer,
    ModuleSerializer,
    LessonSerializer,
    QuizSerializer,
    QuestionSerializer,
    OptionSerializer,
    AssignmentSerializer,
    EnrollmentSerializer,
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
        base_qs = Course.objects.select_related(
            "category", "teacher", "teacher__user"
        ).prefetch_related(
            Prefetch("modules", queryset=Module.objects.order_by("order")),
            Prefetch("modules__lessons", queryset=Lesson.objects.order_by("order")),
            "modules__lessons__quiz_details__questions__options",
            "modules__lessons__assignment_details",
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


@extend_schema_view(
    list=extend_schema(
        summary="List enrollments",
        parameters=[
            OpenApiParameter(
                name="user",
                description="Filter by user ID (admin only)",
                required=False,
                type=int,
            ),
            OpenApiParameter(
                name="course",
                description="Filter by course ID",
                required=False,
                type=int,
            ),
        ],
        responses={200: EnrollmentSerializer(many=True)},
    ),
    create=extend_schema(
        summary="Enroll in a course",
        request=EnrollmentSerializer,
        responses={201: EnrollmentSerializer},
    ),
    retrieve=extend_schema(
        summary="Get enrollment detail",
        responses={200: EnrollmentSerializer},
    ),
    update=extend_schema(
        summary="Update enrollment",
        request=EnrollmentSerializer,
        responses={200: EnrollmentSerializer},
    ),
    partial_update=extend_schema(
        summary="Partially update enrollment",
        request=EnrollmentSerializer,
        responses={200: EnrollmentSerializer},
    ),
    destroy=extend_schema(
        summary="Delete enrollment",
        responses={204: None},
    ),
)
class EnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = EnrollmentSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.role == "admin":
            queryset = Enrollment.objects.all()
            # Admin can filter by user id
            user_id = self.request.query_params.get("user")
            if user_id:
                queryset = queryset.filter(user__id=user_id)
            return queryset
        return Enrollment.objects.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class BundleViewSet(viewsets.ModelViewSet):
    serializer_class = BundleSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["is_active"]

    def get_queryset(self):
        return Bundle.objects.prefetch_related("courses").all()

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]


class ScholarshipViewSet(viewsets.ModelViewSet):
    serializer_class = ScholarshipSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "course"]

    def get_queryset(self):
        return Scholarship.objects.select_related(
            "course", "user", "reviewed_by"
        ).prefetch_related("documents").all()

    def get_permissions(self):
        if self.action in ("create", "upload_documents"):
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]

    @extend_schema(
        request=inline_serializer(
            name="ScholarshipCreateRequest",
            fields={
                "course": drf_fields.IntegerField(),
                "name": drf_fields.CharField(),
                "email": drf_fields.EmailField(),
                "phone_number": drf_fields.CharField(),
                "address": drf_fields.CharField(),
                "current_level_of_study": drf_fields.ChoiceField(choices=["high school", "undergrad", "postgrad", "other"]),
                "field_of_study": drf_fields.CharField(),
                "why_applying": drf_fields.CharField(),
                "how_will_it_help": drf_fields.CharField(),
                "agree_to_contact": drf_fields.BooleanField(),
                "documents": drf_fields.ListField(
                    child=drf_fields.FileField(),
                    required=False,
                    help_text="One or more supporting documents (repeat key for multiple files)",
                ),
            },
        ),
        responses={201: ScholarshipSerializer},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        scholarship = serializer.save(user=self.request.user)
        files = self.request.FILES.getlist("documents")
        if files:
            from courses.models import ScholarshipDocument
            ScholarshipDocument.objects.bulk_create([
                ScholarshipDocument(scholarship=scholarship, file=f) for f in files
            ])

    @extend_schema(
        request=ScholarshipDocumentSerializer(many=True),
        responses={201: ScholarshipDocumentSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="documents")
    def upload_documents(self, request, pk=None):
        """
        POST /scholarships/{id}/documents/
        Student — upload one or more supporting documents.
        Send as multipart/form-data with multiple 'file' fields.
        """
        scholarship = self.get_object()

        if scholarship.user != request.user:
            return Response(
                {"error": "You can only upload documents for your own application."},
                status=status.HTTP_403_FORBIDDEN,
            )

        files = request.FILES.getlist("file")
        if not files:
            return Response(
                {"error": "No files provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from courses.models import ScholarshipDocument
        documents = [
            ScholarshipDocument(scholarship=scholarship, file=f) for f in files
        ]
        ScholarshipDocument.objects.bulk_create(documents)
        created = scholarship.documents.order_by("-uploaded_at")[:len(files)]
        return Response(
            ScholarshipDocumentSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=ApproveScholarshipSerializer, responses={200: ScholarshipSerializer})
    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """
        POST /scholarships/{id}/approve/
        Admin — approve a scholarship application with a discount percentage.
        Body: { "discount_percent": 50 }
        """
        scholarship = self.get_object()

        if scholarship.status != "pending":
            return Response(
                {"error": f"Cannot approve a scholarship that is already '{scholarship.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ApproveScholarshipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        scholarship.status = "approved"
        scholarship.discount_percent = serializer.validated_data["discount_percent"]
        scholarship.reviewed_by = request.user
        scholarship.reviewed_at = timezone.now()
        scholarship.rejection_note = None
        scholarship.save()

        return Response(ScholarshipSerializer(scholarship).data)

    @extend_schema(request=RejectScholarshipSerializer, responses={200: ScholarshipSerializer})
    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        """
        POST /scholarships/{id}/reject/
        Admin — reject a scholarship application with an optional note.
        Body: { "rejection_note": "..." }
        """
        scholarship = self.get_object()

        if scholarship.status != "pending":
            return Response(
                {"error": f"Cannot reject a scholarship that is already '{scholarship.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RejectScholarshipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        scholarship.status = "rejected"
        scholarship.rejection_note = serializer.validated_data.get("rejection_note", "")
        scholarship.reviewed_by = request.user
        scholarship.reviewed_at = timezone.now()
        scholarship.save()

        return Response(ScholarshipSerializer(scholarship).data)


class CourseCategoryViewSet(viewsets.ModelViewSet):
    queryset = CourseCategory.objects.all()
    serializer_class = CourseCategorySerializer


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

    # courses/views.py
    @action(detail=True, methods=["post"], url_path="complete")
    def complete_lesson(self, request, pk=None):
        """
        POST /lessons/{id}/complete/
        Student marks a lesson as complete.
        """
        lesson = self.get_object()

        # Must be enrolled
        enrollment = Enrollment.objects.filter(
            user=request.user, course=lesson.module.course
        ).first()

        if not enrollment:
            return Response(
                {"error": "You are not enrolled in this course."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Mark lesson complete
        _, created = LessonCompletion.objects.get_or_create(
            user=request.user, lesson=lesson
        )

        # Check if course is now complete
        course_completed = enrollment.check_completion()

        return Response(
            {
                "lesson_completed": True,
                "already_completed": not created,
                "course_completed": course_completed,
                "progress_percent": enrollment.progress_percent,
            }
        )


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
