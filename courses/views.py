from courses.models import LessonCompletion
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Prefetch, Max
import django_filters
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view, inline_serializer
from drf_spectacular.openapi import AutoSchema
from rest_framework import fields as drf_fields
from accounts.models import TeacherProfile
from config.permissions import IsAdminRole, IsAdminOrTeacher
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
    QuizAttempt,
    QuizAnswer,
    AssignmentSubmission,
)
from .serializers import (
    CourseSerializer,
    CourseListSerializer,
    BundleSerializer,
    ScholarshipSerializer,
    ScholarshipDocumentSerializer,
    ApproveScholarshipSerializer,
    RejectScholarshipSerializer,
    CourseCategorySerializer,
    ModuleSerializer,
    LessonSerializer,
    LiveLessonSerializer,
    QuizSerializer,
    QuestionSerializer,
    OptionSerializer,
    AssignmentSerializer,
    EnrollmentSerializer,
    QuizSubmitSerializer,
    QuizAttemptResultSerializer,
    QuizAttemptListSerializer,
    AssignmentSubmissionCreateSerializer,
    AssignmentSubmissionReviewSerializer,
    AssignmentSubmissionSerializer,
)


def user_has_course_access(user, course):
    """Return True if the user can access course content — either enrolled or has active membership."""
    if Enrollment.objects.filter(user=user, course=course).exists():
        return True
    return hasattr(user, "membership") and user.membership.is_currently_active


class CourseFilter(django_filters.FilterSet):
    teacher = django_filters.ModelChoiceFilter(
        queryset=TeacherProfile.objects.select_related("user").all()
    )

    class Meta:
        model = Course
        fields = ["category", "status", "teacher"]


@extend_schema_view(
    list=extend_schema(
        description=(
            "List courses. Results are filtered by role:\n\n"
            "- **Admin / staff** — all courses (active and inactive).\n"
            "- **Teacher** — only courses assigned to the authenticated teacher.\n"
            "- **Student / unauthenticated** — active courses only."
        )
    )
)
class CourseViewSet(viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = CourseFilter
    search_fields = ["title", "subtitle", "description"]

    def get_serializer_class(self):
        if self.action == 'list':
            return CourseListSerializer
        return CourseSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            ctx['enrolled_course_ids'] = set(
                Enrollment.objects.filter(user=user).values_list('course_id', flat=True)
            )
            ctx['has_active_membership'] = (
                hasattr(user, 'membership') and user.membership.is_currently_active
            )
        else:
            ctx['enrolled_course_ids'] = set()
            ctx['has_active_membership'] = False
        return ctx

    def get_queryset(self):
        from django.db.models import Count
        user = self.request.user

        if self.action == 'list':
            base_qs = Course.objects.select_related(
                "category", "teacher", "teacher__user"
            ).annotate(total_lessons_count=Count('modules__lessons', distinct=True))
        else:
            base_qs = Course.objects.select_related(
                "category", "teacher", "teacher__user"
            ).prefetch_related(
                Prefetch("modules", queryset=Module.objects.order_by("order")),
                Prefetch("modules__lessons", queryset=Lesson.objects.order_by("order")),
                "modules__lessons__quiz_details__questions__options",
                "modules__lessons__assignment_details",
            )

        if not user.is_authenticated:
            return base_qs.filter(is_active=True)

        role = getattr(user, "role", None)

        if role == "admin" or user.is_staff:
            return base_qs.all()

        if role == "teacher":
            return base_qs.filter(teacher__user=user)

        return base_qs.filter(is_active=True)

    def retrieve(self, request, *args, **kwargs):
        from django.db.models import Count
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Related: same category first, then fill up with same level
        related_qs = list(
            Course.objects.filter(is_active=True, category=instance.category)
            .exclude(pk=instance.pk)
            .select_related("category", "teacher", "teacher__user")
            .annotate(total_lessons_count=Count("modules__lessons", distinct=True))[:4]
        )
        if len(related_qs) < 4:
            exclude_ids = [instance.pk] + [c.pk for c in related_qs]
            fallback = list(
                Course.objects.filter(is_active=True, level=instance.level)
                .exclude(pk__in=exclude_ids)
                .select_related("category", "teacher", "teacher__user")
                .annotate(total_lessons_count=Count("modules__lessons", distinct=True))
                [:4 - len(related_qs)]
            )
            related_qs += fallback

        data["related_courses"] = CourseListSerializer(
            related_qs, many=True, context=self.get_serializer_context()
        ).data

        return Response(data)

    @action(detail=True, methods=["get"], url_path="certificate", permission_classes=[permissions.IsAuthenticated])
    def certificate(self, request, pk=None):
        """
        GET /courses/{id}/certificate/
        Student — retrieve their issued certificate for this course.
        Returns the certificate details and PDF download URL.
        """
        from certificates.models import Certificate
        from certificates.serializers import CertificateSerializer

        course = self.get_object()
        try:
            cert = Certificate.objects.select_related("course", "template").get(
                student=request.user, course=course
            )
        except Certificate.DoesNotExist:
            return Response(
                {"detail": "No certificate has been issued for this course yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(CertificateSerializer(cert).data)


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
            queryset = Enrollment.objects.select_related("user", "user__student_profile", "course")
            # Admin can filter by user id
            user_id = self.request.query_params.get("user")
            if user_id:
                queryset = queryset.filter(user__id=user_id)
            return queryset
        return Enrollment.objects.select_related("user", "user__student_profile", "course").filter(user=user)

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_staff or user.role == "admin":
            # Admin can enroll any user; default to self if user not specified
            serializer.save()
            return
        # Students can self-enroll only with an active membership
        has_membership = hasattr(user, "membership") and user.membership.is_currently_active
        if not has_membership:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("An active membership is required to enroll for free.")
        serializer.save(user=user)


class BundleViewSet(viewsets.ModelViewSet):
    serializer_class = BundleSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["is_active"]

    def get_queryset(self):
        qs = Bundle.objects.prefetch_related("courses").all()
        if not self.request.user or not self.request.user.is_staff:
            qs = qs.filter(is_active=True)
        return qs

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
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

    def get_queryset(self):
        from django.core.cache import cache
        cached = cache.get('course_categories')
        if cached is None:
            cached = list(CourseCategory.objects.all())
            cache.set('course_categories', cached, 60 * 60 * 24)  # 24 hours
        return cached

    def _invalidate_category_cache(self):
        from django.core.cache import cache
        cache.delete('course_categories')

    def perform_create(self, serializer):
        serializer.save()
        self._invalidate_category_cache()

    def perform_update(self, serializer):
        serializer.save()
        self._invalidate_category_cache()

    def perform_destroy(self, instance):
        instance.delete()
        self._invalidate_category_cache()


class ModuleViewSet(viewsets.ModelViewSet):
    serializer_class = ModuleSerializer

    def get_queryset(self):
        queryset = Module.objects.select_related("course").order_by("order").all()
        if "course_pk" in self.kwargs:
            queryset = queryset.filter(course_id=self.kwargs["course_pk"])
        return queryset

    def perform_create(self, serializer):
        if "course_pk" in self.kwargs:
            course_id = self.kwargs["course_pk"]
            next_order = (
                Module.objects.filter(course_id=course_id).aggregate(
                    Max("order")
                )["order__max"] or 0
            ) + 1
            serializer.save(course_id=course_id, order=next_order)
        else:
            serializer.save()

    @extend_schema(
        request=inline_serializer(
            name="ModuleReorderInput",
            fields={
                "order": drf_fields.ListField(
                    child=inline_serializer(
                        name="ModuleReorderItem",
                        fields={
                            "id": drf_fields.IntegerField(),
                            "order": drf_fields.IntegerField(),
                        },
                    )
                )
            },
        ),
        responses={200: ModuleSerializer(many=True)},
        summary="Bulk reorder modules within a course",
    )
    @action(detail=False, methods=["post"], url_path="reorder", permission_classes=[IsAdminRole])
    def reorder(self, request, *args, **kwargs):
        items = request.data.get("order", [])
        if not items:
            return Response({"detail": "Provide 'order' list of {id, order}."}, status=status.HTTP_400_BAD_REQUEST)

        course_id = self.kwargs.get("course_pk")
        for item in items:
            Module.objects.filter(pk=item["id"], course_id=course_id).update(order=item["order"])

        queryset = self.get_queryset().order_by("order")
        return Response(ModuleSerializer(queryset, many=True, context=self.get_serializer_context()).data)


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

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            ctx['enrolled_course_ids'] = set(
                Enrollment.objects.filter(user=user).values_list('course_id', flat=True)
            )
            ctx['has_active_membership'] = (
                hasattr(user, 'membership') and user.membership.is_currently_active
            )
        else:
            ctx['enrolled_course_ids'] = set()
            ctx['has_active_membership'] = False
        return ctx

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdminRole()]
        return [permissions.IsAuthenticated()]

    def retrieve(self, request, *args, **kwargs):
        lesson = self.get_object()
        user = request.user

        is_admin_or_teacher = (
            user.is_staff
            or getattr(user, "role", None) == "admin"
            or (
                lesson.module.course.teacher
                and lesson.module.course.teacher.user == user
            )
        )
        is_enrolled = Enrollment.objects.filter(
            user=user, course=lesson.module.course
        ).exists()

        has_membership = (
            not is_enrolled
            and hasattr(user, "membership")
            and user.membership.is_currently_active
        )

        if not lesson.is_preview and not is_enrolled and not has_membership and not is_admin_or_teacher:
            return Response(
                {"error": "You must be enrolled in this course to access this lesson."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(lesson)
        return Response(serializer.data)

    def perform_create(self, serializer):
        if "module_pk" in self.kwargs:
            module_id = self.kwargs["module_pk"]
            next_order = (
                Lesson.objects.filter(module_id=module_id).aggregate(
                    Max("order")
                )["order__max"] or 0
            ) + 1
            serializer.save(module_id=module_id, order=next_order)
        else:
            serializer.save()

    @extend_schema(
        request=inline_serializer(
            name="LessonReorderInput",
            fields={
                "order": drf_fields.ListField(
                    child=inline_serializer(
                        name="LessonReorderItem",
                        fields={
                            "id": drf_fields.IntegerField(),
                            "order": drf_fields.IntegerField(),
                        },
                    )
                )
            },
        ),
        responses={200: LessonSerializer(many=True)},
        summary="Bulk reorder lessons within a module",
    )
    @action(detail=False, methods=["post"], url_path="reorder", permission_classes=[IsAdminRole])
    def reorder(self, request, *args, **kwargs):
        items = request.data.get("order", [])
        if not items:
            return Response({"detail": "Provide 'order' list of {id, order}."}, status=status.HTTP_400_BAD_REQUEST)

        module_id = self.kwargs.get("module_pk")
        for item in items:
            Lesson.objects.filter(pk=item["id"], module_id=module_id).update(order=item["order"])

        queryset = self.get_queryset().order_by("order")
        return Response(LessonSerializer(queryset, many=True, context=self.get_serializer_context()).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        lesson = serializer.instance
        response_data = serializer.data

        # Auto-initialize Bunny video entry for video-type lessons
        if lesson.content_type == "video":
            try:
                from config.bunny_stream import create_video
                result = create_video(lesson.title)
                video_id = result["video_id"]
                embed_url = (
                    f"https://iframe.mediadelivery.net/embed/"
                    f"{settings.BUNNY_STREAM_LIBRARY_ID}/{video_id}"
                )
                lesson.bunny_video_id = video_id
                lesson.bunny_video_status = "created"
                lesson.video_content = embed_url
                lesson.save(update_fields=["bunny_video_id", "bunny_video_status", "video_content"])
                response_data = dict(response_data)
                response_data["video_upload"] = {
                    "video_id": video_id,
                    "upload_url": result["upload_url"],
                    "upload_method": "PUT",
                    "upload_headers": {
                        "AccessKey": settings.BUNNY_STREAM_API_KEY,
                        "Content-Type": "video/*",
                    },
                }
            except Exception as e:
                # Don't fail lesson creation if Bunny is unreachable; admin can retry via POST /video/
                response_data = dict(response_data)
                response_data["video_upload"] = None
                response_data["video_upload_error"] = f"Lesson created but Bunny init failed: {e}"

        headers = self.get_success_headers(serializer.data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)


    @action(detail=True, methods=["get"], url_path="zoom-link", permission_classes=[permissions.IsAuthenticated])
    def zoom_link(self, request, pk=None, **kwargs):
        """
        GET /lessons/{id}/zoom-link/
        Returns the Zoom link for a live lesson.
        - Teacher/admin: gets a fresh start_url (host link) fetched live from Zoom.
        - Student: gets the join_url (attendee link).
        """
        lesson = self.get_object()

        if lesson.content_type != "live":
            return Response({"error": "This lesson is not a live session."}, status=status.HTTP_400_BAD_REQUEST)

        if not lesson.zoom_meeting_id:
            return Response({"error": "No Zoom meeting has been created for this lesson yet."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_host = (
            user.is_staff
            or getattr(user, "role", None) == "admin"
            or (lesson.module.course.teacher and lesson.module.course.teacher.user == user)
        )

        if is_host:
            # Fetch a fresh start_url — the stored one expires after ~2 hours
            try:
                import requests as http_requests
                from config.zoom import _headers
                resp = http_requests.get(
                    f"https://api.zoom.us/v2/meetings/{lesson.zoom_meeting_id}",
                    headers=_headers(),
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                return Response({
                    "type": "host",
                    "url": data["start_url"],
                    "scheduled_at": lesson.scheduled_at,
                })
            except Exception as e:
                return Response({"error": f"Could not fetch Zoom meeting: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

        # Student — check access first
        is_enrolled = Enrollment.objects.filter(user=user, course=lesson.module.course).exists()
        has_membership = hasattr(user, "membership") and user.membership.is_currently_active
        if not is_enrolled and not has_membership and not lesson.is_preview:
            return Response({"error": "You must be enrolled to access this lesson."}, status=status.HTTP_403_FORBIDDEN)

        return Response({
            "type": "attendee",
            "url": lesson.zoom_join_url,
            "scheduled_at": lesson.scheduled_at,
        })

    @action(detail=True, methods=["get", "post", "delete"], url_path="video",
            permission_classes=[IsAdminOrTeacher])
    def video(self, request, *args, **kwargs):
        """
        Manage the Bunny Stream video for this lesson.

        GET  → Returns current video status and playback URLs (or 404 if no video).
        POST → Initializes a new Bunny video and returns direct-upload credentials.
               Any existing video is deleted first.
               Frontend must then PUT the raw file to `upload_url` using `upload_headers`.
        DELETE → Deletes the video from Bunny Stream and clears the lesson's video fields.
        """
        lesson = self.get_object()

        if request.method == "GET":
            return self._get_video(lesson)
        if request.method == "POST":
            return self._init_video(request, lesson)
        if request.method == "DELETE":
            return self._delete_video(lesson)

    def _get_video(self, lesson):
        if not lesson.bunny_video_id:
            return Response(
                {"detail": "No video has been uploaded for this lesson yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        from config.bunny_stream import get_video
        try:
            info = get_video(lesson.bunny_video_id)
        except Exception as e:
            return Response(
                {"detail": f"Failed to fetch video info from Bunny: {e}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        # Sync status + backfill video_content if it's ready but wasn't set
        update_fields = []
        if info["status_label"] != lesson.bunny_video_status:
            lesson.bunny_video_status = info["status_label"]
            update_fields.append("bunny_video_status")
        if info["status_label"] == "ready" and not lesson.video_content:
            lesson.video_content = info["embed_url"]
            update_fields.append("video_content")
        if update_fields:
            lesson.save(update_fields=update_fields)
        return Response({
            "video_id": lesson.bunny_video_id,
            "status": info["status_label"],   # created|uploaded|processing|transcoding|ready|error|upload_failed
            "embed_url": info["embed_url"],   # use this in an <iframe> to play the video
            "hls_url": info["hls_url"],       # HLS stream URL for custom players
            "thumbnail_url": info["thumbnail_url"],
            "duration_seconds": info["duration_seconds"],
        })

    def _init_video(self, request, lesson):
        from config.bunny_stream import create_video, delete_video
        # Replace existing video if one exists
        if lesson.bunny_video_id:
            delete_video(lesson.bunny_video_id)

        title = request.data.get("title") or lesson.title
        try:
            result = create_video(title)
        except Exception as e:
            return Response(
                {"detail": f"Failed to create video on Bunny Stream: {e}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        video_id = result["video_id"]
        embed_url = f"https://iframe.mediadelivery.net/embed/{settings.BUNNY_STREAM_LIBRARY_ID}/{video_id}"

        lesson.bunny_video_id = video_id
        lesson.bunny_video_status = "created"
        lesson.video_content = embed_url
        lesson.save(update_fields=["bunny_video_id", "bunny_video_status", "video_content"])

        return Response({
            "video_id": video_id,
            "video_content": embed_url,       # already saved on lesson; frontend can use immediately once status=ready
            # PUT the raw video file directly to this URL (do NOT send to our server)
            "upload_url": result["upload_url"],
            "upload_method": "PUT",
            "upload_headers": {
                "AccessKey": settings.BUNNY_STREAM_API_KEY,
                "Content-Type": "video/*",
            },
        }, status=status.HTTP_201_CREATED)

    def _delete_video(self, lesson):
        if not lesson.bunny_video_id:
            return Response(
                {"detail": "No video to delete."},
                status=status.HTTP_404_NOT_FOUND,
            )
        from config.bunny_stream import delete_video
        delete_video(lesson.bunny_video_id)
        lesson.bunny_video_id = ""
        lesson.bunny_video_status = ""
        lesson.video_content = ""
        lesson.save(update_fields=["bunny_video_id", "bunny_video_status", "video_content"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    # courses/views.py
    @action(detail=True, methods=["post"], url_path="complete")
    def complete_lesson(self, request, pk=None):
        """
        POST /lessons/{id}/complete/
        Student marks a lesson as complete.
        """
        lesson = self.get_object()

        # Must be enrolled or have active membership
        if not user_has_course_access(request.user, lesson.module.course):
            return Response(
                {"error": "You are not enrolled in this course."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Mark lesson complete
        _, created = LessonCompletion.objects.get_or_create(
            user=request.user, lesson=lesson
        )

        # Check if course is now complete (only possible for enrolled users, not membership-only)
        enrollment = Enrollment.objects.filter(
            user=request.user, course=lesson.module.course
        ).first()
        course_completed = enrollment.check_completion() if enrollment else False

        return Response(
            {
                "lesson_completed": True,
                "already_completed": not created,
                "course_completed": course_completed,
                "progress_percent": enrollment.progress_percent if enrollment else None,
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

    def get_permissions(self):
        if self.action in ("submit", "my_attempts"):
            return [permissions.IsAuthenticated()]
        if self.action in ("list", "retrieve"):
            return [IsAdminOrTeacher()]
        return [IsAdminRole()]

    @extend_schema(
        request=QuizSubmitSerializer,
        responses={201: QuizAttemptResultSerializer},
        summary="Submit quiz answers",
        description=(
            "Student submits answers for a quiz. Multiple attempts are allowed. "
            "Returns score (%) and pass/fail only — correct answers are never exposed."
        ),
    )
    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, *args, **kwargs):
        """
        POST /courses/{slug}/modules/{m}/lessons/{l}/quizzes/{pk}/submit/
        Student submits quiz answers. Multiple attempts are allowed.
        Returns score percentage and pass/fail — never exposes correct answers.
        """
        quiz = self.get_object()

        # Verify enrollment or active membership
        if not user_has_course_access(request.user, quiz.lesson.module.course):
            return Response(
                {"error": "You are not enrolled in this course."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = QuizSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answers = serializer.validated_data["answers"]

        # Score the attempt
        questions = {q.id: q for q in quiz.questions.prefetch_related("options")}
        total_points = sum(q.points for q in questions.values())
        earned_points = 0

        answer_map = {a["question"].id: a["selected_option"] for a in answers}

        for question_id, question in questions.items():
            chosen = answer_map.get(question_id)
            if chosen and chosen.is_correct:
                earned_points += question.points

        score = round((earned_points / total_points * 100), 2) if total_points else 0
        passed = score >= quiz.passing_score

        # Persist attempt
        attempt = QuizAttempt.objects.create(
            user=request.user, quiz=quiz, score=score, passed=passed
        )
        for question_id, option in answer_map.items():
            if question_id in questions:
                QuizAnswer.objects.create(
                    attempt=attempt,
                    question_id=question_id,
                    selected_option=option,
                )

        # Auto-mark lesson complete and check course completion on pass
        if passed:
            LessonCompletion.objects.get_or_create(user=request.user, lesson=quiz.lesson)
            enrollment = Enrollment.objects.filter(
                user=request.user, course=quiz.lesson.module.course
            ).first()
            if enrollment:
                enrollment.check_completion()

        result = QuizAttemptResultSerializer(attempt).data
        return Response(result, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={200: QuizAttemptListSerializer(many=True)},
        summary="My quiz attempts",
        description="Returns the student's past attempt scores. Correct answers are never exposed.",
    )
    @action(detail=True, methods=["get"], url_path="my-attempts")
    def my_attempts(self, request, *args, **kwargs):
        """
        GET /courses/{slug}/modules/{m}/lessons/{l}/quizzes/{pk}/my-attempts/
        Returns the student's past attempt scores (no correct/wrong answers exposed).
        """
        quiz = self.get_object()
        attempts = QuizAttempt.objects.filter(user=request.user, quiz=quiz)
        serializer = QuizAttemptListSerializer(attempts, many=True)
        return Response(serializer.data)


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

    def get_permissions(self):
        if self.action in ("submit", "my_submissions"):
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]

    @extend_schema(
        request=AssignmentSubmissionCreateSerializer,
        responses={201: AssignmentSubmissionSerializer},
        summary="Submit assignment",
        description=(
            "Student submits their assignment (file and/or text). "
            "Only one active (pending/approved) submission per assignment is allowed; "
            "rejected submissions can be resubmitted."
        ),
    )
    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, *args, **kwargs):
        """
        POST /courses/{slug}/modules/{m}/lessons/{l}/assignments/{pk}/submit/
        Student submits their assignment. Only one active (pending/approved) submission
        per student per assignment is allowed; rejected submissions can be resubmitted.
        """
        assignment = self.get_object()

        if not user_has_course_access(request.user, assignment.lesson.module.course):
            return Response(
                {"error": "You are not enrolled in this course."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Prevent duplicate pending/approved submissions
        existing = AssignmentSubmission.objects.filter(
            user=request.user,
            assignment=assignment,
            status__in=[AssignmentSubmission.Status.PENDING, AssignmentSubmission.Status.APPROVED],
        ).first()
        if existing:
            return Response(
                {"error": "You already have an active submission for this assignment."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AssignmentSubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = serializer.save(user=request.user, assignment=assignment)

        return Response(
            AssignmentSubmissionSerializer(submission).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        responses={200: AssignmentSubmissionSerializer(many=True)},
        summary="My assignment submissions",
        description="Returns the student's own submissions for this assignment.",
    )
    @action(detail=True, methods=["get"], url_path="my-submissions")
    def my_submissions(self, request, *args, **kwargs):
        """
        GET /courses/{slug}/modules/{m}/lessons/{l}/assignments/{pk}/my-submissions/
        Returns the student's own submissions for this assignment.
        """
        assignment = self.get_object()
        submissions = AssignmentSubmission.objects.filter(
            user=request.user, assignment=assignment
        )
        serializer = AssignmentSubmissionSerializer(submissions, many=True)
        return Response(serializer.data)


class AssignmentSubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admin/teacher viewset for reviewing assignment submissions.
    GET  /assignment-submissions/               → list all (filter by ?assignment=, ?status=)
    GET  /assignment-submissions/{id}/          → detail
    POST /assignment-submissions/{id}/review/   → approve or reject with feedback
    """

    serializer_class = AssignmentSubmissionSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["assignment", "status", "user"]

    def get_queryset(self):
        return AssignmentSubmission.objects.select_related(
            "user", "assignment__lesson", "reviewed_by"
        ).all()

    def get_permissions(self):
        return [IsAdminOrTeacher()]

    @extend_schema(
        request=AssignmentSubmissionReviewSerializer,
        responses={200: AssignmentSubmissionSerializer},
        summary="Review assignment submission",
        description="Admin or teacher approves or rejects a submission with optional feedback and mark.",
    )
    @action(detail=True, methods=["patch"], url_path="review")
    def review(self, request, pk=None):
        """
        PATCH /assignment-submissions/{id}/review/
        Body: { "status": "approved"|"rejected", "teacher_feedback": "...", "mark": 85 }
        """
        submission = self.get_object()
        serializer = AssignmentSubmissionReviewSerializer(
            submission, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        submission = serializer.save(reviewed_by=request.user, reviewed_at=timezone.now())

        # If approved, check for course completion
        if submission.status == AssignmentSubmission.Status.APPROVED:
            enrollment = Enrollment.objects.filter(
                user=submission.user, course=submission.assignment.lesson.module.course
            ).first()
            if enrollment:
                enrollment.check_completion()

        return Response(AssignmentSubmissionSerializer(submission).data)


@extend_schema_view(
    list=extend_schema(
        summary="List teacher live sessions",
        description=(
            "Returns all live lessons belonging to the authenticated teacher's courses, "
            "ordered by scheduled time (soonest first).\n\n"
            "**Permissions:** Teacher or Admin only.\n\n"
            "**Role behaviour:**\n"
            "- Teacher — only sees live lessons from their own courses.\n"
            "- Admin/staff — sees all live lessons across all courses.\n\n"
            "**`?status` filter values:**\n"
            "| Value | Description |\n"
            "|---|---|\n"
            "| `upcoming` | `scheduled_at` is in the future |\n"
            "| `live` | session has started but may not have ended |\n"
            "| `completed` | `scheduled_at` is in the past |\n\n"
            "**`live_status` field on each item** (computed):\n"
            "| Value | Meaning |\n"
            "|---|---|\n"
            "| `scheduled` | More than 30 min before start |\n"
            "| `upcoming` | Within 30 min of start |\n"
            "| `live` | Currently in progress |\n"
            "| `completed` | Session ended |\n"
            "| `null` | No `scheduled_at` set |\n\n"
            "Use `zoom_start_url` for the **Start Session** button (host link).\n"
            "Use `zoom_join_url` for the student join link."
        ),
        parameters=[
            OpenApiParameter(
                name="status",
                description="Filter by session state: `upcoming`, `live`, or `completed`.",
                required=False,
                type=str,
                enum=["upcoming", "live", "completed"],
            )
        ],
        responses={200: LiveLessonSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Get a single live session",
        description=(
            "Returns full details for one live lesson, including Zoom URLs and `live_status`.\n\n"
            "**Permissions:** Teacher or Admin only."
        ),
        responses={200: LiveLessonSerializer},
    ),
)
class TeacherLiveSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /teacher/live-sessions/         → all live lessons for the authenticated teacher
    GET /teacher/live-sessions/?status=upcoming  → filter by status (scheduled|upcoming|live|completed)
    """
    serializer_class = LiveLessonSerializer

    def get_permissions(self):
        return [IsAdminOrTeacher()]

    def get_queryset(self):
        user = self.request.user
        qs = (
            Lesson.objects.filter(content_type="live")
            .select_related("module", "module__course", "module__course__teacher")
            .prefetch_related("module__course__enrollments")
            .order_by("scheduled_at")
        )
        if user.is_staff or getattr(user, "role", None) == "admin":
            pass  # admins see all
        else:
            qs = qs.filter(module__course__teacher__user=user)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            now = timezone.now()
            if status_filter == "upcoming":
                qs = qs.filter(scheduled_at__gt=now)
            elif status_filter == "live":
                from django.db.models import F, ExpressionWrapper, DurationField
                # roughly: scheduled_at <= now <= scheduled_at + duration
                qs = qs.filter(scheduled_at__lte=now)
            elif status_filter == "completed":
                qs = qs.filter(scheduled_at__lt=now)

        return qs


class TeacherDashboardView(viewsets.ViewSet):
    """
    GET /teacher/dashboard/
    Returns stats and lists for the teacher dashboard:
      - active_courses, live_sessions_today
      - upcoming_live_sessions (next 5)
      - recent_uploads (last 5 non-live lessons)
    """

    def get_permissions(self):
        return [IsAdminOrTeacher()]

    @extend_schema(
        summary="Teacher dashboard summary",
        description=(
            "Returns a stats overview and content lists for the teacher's dashboard.\n\n"
            "**Permissions:** Teacher or Admin only.\n\n"
            "**Role behaviour:**\n"
            "- Teacher — scoped to their own active courses.\n"
            "- Admin/staff — scoped to all active courses.\n\n"
            "**Stats fields:**\n"
            "| Field | Description |\n"
            "|---|---|\n"
            "| `active_courses` | Number of published courses assigned to this teacher |\n"
            "| `live_sessions_today` | Live lessons scheduled for today (UTC) |\n\n"
            "**`upcoming_live_sessions`** — next 5 live lessons, soonest first. "
            "Each item includes `live_status`, `enrolled_count`, `zoom_start_url`, "
            "`scheduled_at`, and `duration_in_minutes`.\n\n"
            "**`recent_uploads`** — last 5 non-live lessons added (by id desc). "
            "Each item includes `id`, `title`, `course_title`, and `content_type` "
            "(`video`, `document`, `quiz`, `assignment`, `external_link`)."
        ),
        responses={
            200: inline_serializer(
                name="TeacherDashboardResponse",
                fields={
                    "active_courses": drf_fields.IntegerField(
                        help_text="Published courses assigned to this teacher."
                    ),
                    "live_sessions_today": drf_fields.IntegerField(
                        help_text="Live lessons scheduled for today (UTC)."
                    ),
                    "upcoming_live_sessions": LiveLessonSerializer(
                        many=True,
                        help_text="Next 5 live lessons, soonest first.",
                    ),
                    "recent_uploads": inline_serializer(
                        name="RecentUploadItem",
                        fields={
                            "id": drf_fields.IntegerField(),
                            "title": drf_fields.CharField(help_text="Lesson title."),
                            "course_title": drf_fields.CharField(
                                help_text="Title of the course this lesson belongs to."
                            ),
                            "content_type": drf_fields.ChoiceField(
                                choices=["video", "document", "quiz", "assignment", "external_link"],
                                help_text="Lesson type (excludes live sessions).",
                            ),
                        },
                        many=True,
                        help_text="Last 5 non-live lessons added, newest first.",
                    ),
                },
            ),
            403: inline_serializer(
                name="TeacherDashboardForbidden",
                fields={"detail": drf_fields.CharField()},
            ),
        },
    )
    def list(self, request):
        user = request.user
        is_admin = user.is_staff or getattr(user, "role", None) == "admin"

        if is_admin:
            courses_qs = Course.objects.filter(is_active=True)
        else:
            courses_qs = Course.objects.filter(
                teacher__user=user, is_active=True
            )

        course_ids = list(courses_qs.values_list("id", flat=True))

        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        live_sessions_today = Lesson.objects.filter(
            content_type="live",
            module__course__id__in=course_ids,
            scheduled_at__gte=today_start,
            scheduled_at__lt=today_end,
        ).count()

        upcoming_qs = (
            Lesson.objects.filter(
                content_type="live",
                module__course__id__in=course_ids,
                scheduled_at__gte=timezone.now(),
            )
            .select_related("module", "module__course", "module__course__teacher")
            .prefetch_related("module__course__enrollments")
            .order_by("scheduled_at")[:5]
        )

        recent_uploads_qs = (
            Lesson.objects.filter(module__course__id__in=course_ids)
            .exclude(content_type="live")
            .select_related("module__course")
            .order_by("-id")[:5]
        )

        recent_uploads = [
            {
                "id": l.id,
                "title": l.title,
                "course_title": l.module.course.title,
                "content_type": l.content_type,
            }
            for l in recent_uploads_qs
        ]

        return Response({
            "active_courses": courses_qs.count(),
            "live_sessions_today": live_sessions_today,
            "upcoming_live_sessions": LiveLessonSerializer(
                upcoming_qs, many=True, context={"request": request}
            ).data,
            "recent_uploads": recent_uploads,
        })
