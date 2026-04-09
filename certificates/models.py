import uuid
from django.db import models


class CertificateTemplate(models.Model):
    """
    HTML template uploaded by admin, assigned to a course.
    Placeholders: {{student_name}}, {{course_name}}, {{course_level}},
                  {{instructor_name}}, {{issue_date}}, {{certificate_id}}
    """

    course = models.OneToOneField(
        "courses.Course", on_delete=models.CASCADE, related_name="certificate_template"
    )
    name = models.CharField(max_length=255)
    html_file = models.FileField(upload_to="certificates/templates/")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_certificate_templates",
    )

    def __str__(self):
        return f"{self.name} — {self.course.title}"


class Certificate(models.Model):
    """
    Issued certificate record. Created when admin issues a certificate.
    """

    student = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="certificates"
    )
    course = models.ForeignKey(
        "courses.Course", on_delete=models.CASCADE, related_name="certificates"
    )
    enrollment = models.OneToOneField(
        "courses.Enrollment", on_delete=models.CASCADE, related_name="certificate"
    )
    certificate_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    pdf_file = models.FileField(upload_to="certificates/issued/", blank=True, null=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="issued_certificates",
    )

    class Meta:
        unique_together = ("student", "course")
        ordering = ["-issued_at"]

    def __str__(self):
        return f"Certificate — {self.student.email} — {self.course.title}"
