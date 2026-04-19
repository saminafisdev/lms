import logging
import requests
from django.conf import settings
from django.core.files.base import ContentFile


def _read_template_html(template):
    """
    Read the HTML template file content.

    django-bunny's _open() returns r.raw from a non-streaming request,
    so r.raw.read() always yields empty bytes. We fetch the file directly
    using requests when Bunny storage is active, and fall back to the
    standard file API for local storage.
    """
    if getattr(settings, "USE_BUNNY_STORAGE", False):
        url = template.html_file.url
        logger = logging.getLogger(__name__)
        logger.warning(f"[CERT] Fetching template from CDN: {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        logger.warning(f"[CERT] Template fetched: status={response.status_code} length={len(response.content)}")
        return response.text
    else:
        with template.html_file.open("rb") as f:
            raw = f.read()
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw


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

    html_content = _read_template_html(template)

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

    logger = logging.getLogger(__name__)

    try:
        html_content = render_certificate_html(template, certificate)
        logger.warning(
            f"[CERT] Rendering PDF: html_length={len(html_content)} "
            f"cert={certificate.certificate_id}"
        )
        pdf_bytes = HTML(string=html_content).write_pdf()
        logger.warning(f"[CERT] PDF generated: size={len(pdf_bytes)} bytes")
        filename = f"certificate_{certificate.certificate_id}.pdf"
        certificate.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)
        return True
    except Exception as e:
        logger.error(
            f"PDF generation failed for certificate {certificate.certificate_id}: {e}"
        )
        return False
