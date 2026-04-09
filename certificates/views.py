import logging
from django.db import models as db_models
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from config.permissions import IsAdminRole
from courses.models import Enrollment
from email_templates.sendgrid import send_email

from .models import Certificate, CertificateTemplate
from .serializers import (
    CertificateSerializer,
    CertificateTemplateSerializer,
    CompletedStudentSerializer,
    IssueCertificateSerializer,
)
from .utils import generate_certificate_pdf

logger = logging.getLogger(__name__)


class CertificateTemplateViewSet(viewsets.ModelViewSet):
    """
    Admin only — manage certificate templates per course.
    Upload an HTML file with placeholders:
    {{student_name}}, {{course_name}}, {{course_level}},
    {{instructor_name}}, {{issue_date}}, {{certificate_id}}
    """

    queryset = CertificateTemplate.objects.select_related("course", "created_by").all()
    serializer_class = CertificateTemplateSerializer
    permission_classes = [IsAdminRole]


class CertificateViewSet(viewsets.ViewSet):
    def get_permissions(self):
        if self.action == "verify":
            return [permissions.AllowAny()]
        if self.action == "my_certificates":
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]

    @extend_schema(responses={200: CertificateSerializer(many=True)})
    def list(self, request):
        """
        GET /certificates/
        Admin — list all issued certificates.
        Filter by course: ?course=1
        Search by student email or name: ?search=john
        """
        queryset = Certificate.objects.select_related(
            "student", "course", "issued_by"
        ).all()

        course_id = request.query_params.get("course")
        if course_id:
            queryset = queryset.filter(course__id=course_id)

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                db_models.Q(student__email__icontains=search)
                | db_models.Q(student__first_name__icontains=search)
                | db_models.Q(course__title__icontains=search)
            )

        return Response(CertificateSerializer(queryset, many=True).data)

    @extend_schema(responses={200: CompletedStudentSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="completed-students")
    def completed_students(self, request):
        """
        GET /certificates/completed-students/?course=1
        Admin — list students who completed a course
        and whether they have received a certificate yet.
        """
        course_id = request.query_params.get("course")
        if not course_id:
            return Response(
                {"error": "course query param is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enrollments = (
            Enrollment.objects.filter(course__id=course_id, is_completed=True)
            .select_related("user")
            .prefetch_related("certificate")
        )

        data = []
        for enrollment in enrollments:
            has_certificate = hasattr(enrollment, "certificate")
            cert = enrollment.certificate if has_certificate else None
            data.append(
                {
                    "enrollment_id": enrollment.id,
                    "student_name": f"{enrollment.user.first_name} {enrollment.user.last_name}".strip()
                    or enrollment.user.email,
                    "student_email": enrollment.user.email,
                    "completed_at": enrollment.completed_at,
                    "has_certificate": has_certificate,
                    "certificate_id": str(cert.certificate_id) if cert else None,
                    "pdf_file": cert.pdf_file.url if cert and cert.pdf_file else None,
                }
            )

        return Response(data)

    @extend_schema(
        request=IssueCertificateSerializer,
        responses={201: CertificateSerializer(many=True)},
    )
    @action(detail=False, methods=["post"], url_path="issue")
    def issue(self, request):
        """
        POST /certificates/issue/
        Admin — issue certificates to selected students.
        Body: { "enrollment_ids": [1, 2, 3] }
        Generates PDF from course template and emails the student.
        """
        serializer = IssueCertificateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        enrollment_ids = serializer.validated_data["enrollment_ids"]
        enrollments = Enrollment.objects.filter(
            id__in=enrollment_ids, is_completed=True
        ).select_related("user", "course", "course__teacher__user")

        if not enrollments.exists():
            return Response(
                {"error": "No valid completed enrollments found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        issued = []
        skipped = []
        failed = []

        for enrollment in enrollments:
            # Skip if already has a certificate
            if Certificate.objects.filter(enrollment=enrollment).exists():
                skipped.append(enrollment.user.email)
                continue

            # Check course has a template
            if not hasattr(enrollment.course, "certificate_template"):
                failed.append(
                    {
                        "email": enrollment.user.email,
                        "reason": f"Course '{enrollment.course.title}' has no certificate template.",
                    }
                )
                continue

            # Create certificate record
            cert = Certificate.objects.create(
                student=enrollment.user,
                course=enrollment.course,
                enrollment=enrollment,
                issued_by=request.user,
            )

            # Generate PDF
            pdf_success = generate_certificate_pdf(cert)
            if not pdf_success:
                failed.append(
                    {"email": enrollment.user.email, "reason": "PDF generation failed."}
                )
                cert.delete()
                continue

            # Send email
            student_name = f"{cert.student.first_name} {cert.student.last_name}".strip()
            send_email(
                to_email=cert.student.email,
                purpose="certificate_issued",
                template_data={
                    "first_name": cert.student.first_name or "there",
                    "course_name": cert.course.title,
                    "certificate_id": str(cert.certificate_id),
                    "download_url": request.build_absolute_uri(cert.pdf_file.url)
                    if cert.pdf_file
                    else "",
                    "verify_url": request.build_absolute_uri(
                        f"/api/certificates/verify/{cert.certificate_id}/"
                    ),
                },
            )

            issued.append(cert)

        return Response(
            {
                "issued": CertificateSerializer(issued, many=True).data,
                "skipped": skipped,
                "failed": failed,
                "message": f"{len(issued)} issued, {len(skipped)} skipped, {len(failed)} failed.",
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={200: None})
    @action(
        detail=False,
        methods=["get"],
        url_path="verify/(?P<certificate_id>[^/.]+)",
        permission_classes=[permissions.AllowAny],
    )
    def verify(self, request, certificate_id=None):
        """
        GET /certificates/verify/{certificate_id}/
        Public — verify a certificate by its UUID.
        """
        try:
            cert = Certificate.objects.select_related("student", "course").get(
                certificate_id=certificate_id
            )
        except Certificate.DoesNotExist:
            return Response(
                {"valid": False, "error": "Certificate not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "valid": True,
                "certificate_id": str(cert.certificate_id),
                "student_name": f"{cert.student.first_name} {cert.student.last_name}".strip(),
                "course_title": cert.course.title,
                "issued_at": cert.issued_at,
            }
        )

    @extend_schema(responses={200: CertificateSerializer(many=True)})
    @action(
        detail=False,
        methods=["get"],
        url_path="my-certificates",
        permission_classes=[permissions.IsAuthenticated],
    )
    def my_certificates(self, request):
        """
        GET /certificates/my-certificates/
        Student — view their own certificates.
        """
        certs = Certificate.objects.filter(student=request.user).select_related(
            "course"
        )
        return Response(CertificateSerializer(certs, many=True).data)
