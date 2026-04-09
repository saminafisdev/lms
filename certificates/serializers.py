from rest_framework import serializers
from .models import Certificate, CertificateTemplate


class CertificateTemplateSerializer(serializers.ModelSerializer):
    created_by_email = serializers.ReadOnlyField(source="created_by.email")

    class Meta:
        model = CertificateTemplate
        fields = [
            "id",
            "name",
            "html_file",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "created_by_email"]

    def validate_html_file(self, value):
        if not value.name.endswith(".html"):
            raise serializers.ValidationError("Only .html files are allowed.")
        return value

    def save(self, **kwargs):
        kwargs["created_by"] = self.context["request"].user
        return super().save(**kwargs)


class CertificateSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_email = serializers.ReadOnlyField(source="student.email")
    course_title = serializers.ReadOnlyField(source="course.title")
    issued_by_email = serializers.ReadOnlyField(source="issued_by.email")
    template_name = serializers.ReadOnlyField(source="template.name")

    class Meta:
        model = Certificate
        fields = [
            "id",
            "certificate_id",
            "student_name",
            "student_email",
            "course_title",
            "template_name",
            "pdf_file",
            "issued_at",
            "issued_by_email",
        ]

    def get_student_name(self, obj):
        name = f"{obj.student.first_name} {obj.student.last_name}".strip()
        return name or obj.student.email


class IssueCertificateSerializer(serializers.Serializer):
    enrollment_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="List of enrollment IDs to issue certificates to",
    )
    template_id = serializers.IntegerField(
        help_text="ID of the certificate template to use"
    )


class CompletedStudentSerializer(serializers.Serializer):
    enrollment_id = serializers.IntegerField()
    student_name = serializers.CharField()
    student_email = serializers.EmailField()
    completed_at = serializers.DateTimeField()
    has_certificate = serializers.BooleanField()
    certificate_id = serializers.UUIDField(allow_null=True)
    pdf_file = serializers.FileField(allow_null=True)
