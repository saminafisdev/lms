import os
from django.utils import timezone
from django.core.files.base import ContentFile


def render_certificate_html(template, certificate):
    """
    Read the HTML template file and replace placeholders
    with actual certificate data.
    """
    instructor = certificate.course.teacher
    instructor_name = ""
    if instructor:
        instructor_name = (
            f"{instructor.user.first_name} {instructor.user.last_name}".strip()
        )
        if not instructor_name:
            instructor_name = instructor.user.email

    student_name = (
        f"{certificate.student.first_name} {certificate.student.last_name}".strip()
    )
    if not student_name:
        student_name = certificate.student.email

    with template.html_file.open("rb") as f:
        raw = f.read()
        html_content = raw.decode("utf-8") if isinstance(raw, bytes) else raw

    placeholders = {
        "{{student_name}}": student_name,
        "{{course_name}}": certificate.course.title,
        "{{course_level}}": certificate.course.get_level_display(),
        "{{instructor_name}}": instructor_name,
        "{{issue_date}}": certificate.issued_at.strftime("%B %d, %Y"),
        "{{certificate_id}}": str(certificate.certificate_id),
    }

    for placeholder, value in placeholders.items():
        html_content = html_content.replace(placeholder, value)

    return html_content


def generate_certificate_pdf(certificate, template):
    """
    Generate PDF using the provided template.
    Saves the PDF to the certificate's pdf_file field.
    Returns True on success, False on failure.
    """
    from weasyprint import HTML
    import logging

    logger = logging.getLogger(__name__)

    try:
        html_content = render_certificate_html(template, certificate)
        pdf_bytes = HTML(string=html_content).write_pdf()
        filename = f"certificate_{certificate.certificate_id}.pdf"
        certificate.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)
        return True
    except Exception as e:
        logger.error(
            f"PDF generation failed for certificate {certificate.certificate_id}: {e}"
        )
        return False
