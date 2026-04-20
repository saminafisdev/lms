import json
import logging
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To
from django.conf import settings

logger = logging.getLogger(__name__)


def get_sendgrid_client():
    return sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)


def fetch_sendgrid_templates():
    """
    Fetch all dynamic templates from SendGrid account.
    Returns a list of {id, name, updated_at} dicts.
    """
    sg = get_sendgrid_client()
    try:
        response = sg.client.templates.get(
            query_params={
                "generations": "dynamic",
                "page_size": "200",
            }  # page_size as string
        )
        data = json.loads(response.body)
        templates = data.get("result", [])
        return [
            {
                "id": t["id"],
                "name": t["name"],
                "updated_at": t.get("updated_at", ""),
                "versions": [
                    {
                        "id": v["id"],
                        "name": v["name"],
                        "subject": v.get("subject", ""),
                        "thumbnail_url": v.get("thumbnail_url", ""),
                        "active": v.get("active") == 1,
                        "updated_at": v.get("updated_at", ""),
                    }
                    for v in t.get("versions", [])
                ],
            }
            for t in templates
        ]
    except Exception as e:
        logger.error(f"Failed to fetch SendGrid templates: {e}")
        return []


def add_contact_to_newsletter(email, first_name="", last_name=""):
    """
    Add or update a contact in SendGrid Marketing Contacts and place them
    on the newsletter list (SENDGRID_NEWSLETTER_LIST_ID).
    No-op if the list ID is not configured.
    """
    list_id = getattr(settings, "SENDGRID_NEWSLETTER_LIST_ID", "")
    if not list_id:
        logger.warning("SENDGRID_NEWSLETTER_LIST_ID not set — skipping contact sync.")
        return False

    sg = get_sendgrid_client()
    body = {
        "contacts": [{"email": email, "first_name": first_name, "last_name": last_name}],
        "list_ids": [list_id],
    }
    try:
        response = sg.client.marketing.contacts.put(request_body=body)
        logger.info(f"SendGrid: added {email} to newsletter list. Status: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"SendGrid: failed to add {email} to newsletter list: {e}")
        return False


def remove_contact_from_newsletter(email):
    """
    Remove a contact from the newsletter list in SendGrid.
    Searches for the contact by email then removes them from the list.
    Does NOT add to global unsubscribes (that would block transactional emails too).
    """
    list_id = getattr(settings, "SENDGRID_NEWSLETTER_LIST_ID", "")
    if not list_id:
        logger.warning("SENDGRID_NEWSLETTER_LIST_ID not set — skipping contact sync.")
        return False

    sg = get_sendgrid_client()
    try:
        search_response = sg.client.marketing.contacts.search.emails.post(
            request_body={"emails": [email]}
        )
        data = json.loads(search_response.body)
        contact = data.get("result", {}).get(email, {})
        contact_id = contact.get("contact", {}).get("id")
        if not contact_id:
            logger.info(f"SendGrid: {email} not found in contacts, nothing to remove.")
            return True

        sg.client.marketing.lists._(list_id).contacts.delete(
            query_params={"contact_ids": contact_id}
        )
        logger.info(f"SendGrid: removed {email} from newsletter list.")
        return True
    except Exception as e:
        logger.error(f"SendGrid: failed to remove {email} from newsletter list: {e}")
        return False


def send_plain_email(to_email, subject, body):
    """
    Send a basic plain-text email via SendGrid without a dynamic template.
    Used as a fallback when no template is configured for a purpose.
    """
    sg = get_sendgrid_client()
    message = Mail(
        from_email=Email(settings.DEFAULT_FROM_EMAIL, settings.DEFAULT_FROM_NAME),
        to_emails=To(to_email),
        subject=subject,
        plain_text_content=body,
    )
    try:
        sg.send(message)
        return True
    except Exception as e:
        logger.error(f"SendGrid failed sending plain email to {to_email}: {e}")
        return False


_FALLBACK_EMAILS = {
    "welcome": (
        "Welcome!",
        lambda d: (
            f"Hi {d.get('first_name', 'there')},\n\n"
            "Welcome! Your account has been created successfully.\n\n"
            "Happy learning!"
        ),
    ),
    "membership_purchase": (
        "Membership Activated",
        lambda d: (
            f"Hi {d.get('first_name', 'there')},\n\n"
            f"Your {d.get('plan_name', 'membership')} has been activated.\n"
            f"It is valid until {d.get('end_date', 'N/A')}.\n\n"
            "Thank you!"
        ),
    ),
    "course_purchase": (
        "Course Purchase Confirmed",
        lambda d: (
            f"Hi {d.get('first_name', 'there')},\n\n"
            f"You now have access to: {d.get('course_name', 'your course')}.\n"
            f"Amount paid: {d.get('amount', '')}\n\n"
            "Happy learning!"
        ),
    ),
    "bundle_purchase": (
        "Bundle Purchase Confirmed",
        lambda d: (
            f"Hi {d.get('first_name', 'there')},\n\n"
            f"You now have access to the {d.get('bundle_name', 'bundle')} bundle.\n"
            f"Courses included: {d.get('course_names', '')}\n"
            f"Amount paid: {d.get('amount', '')}\n\n"
            "Happy learning!"
        ),
    ),
    "book_purchase": (
        "Book Purchase Confirmed",
        lambda d: (
            f"Hi {d.get('first_name', 'there')},\n\n"
            f"Thank you for purchasing: {d.get('book_title', 'your book')}.\n"
            f"Format: {d.get('format', '')}\n"
            f"Amount paid: {d.get('amount', '')}\n\n"
            "Enjoy your read!"
        ),
    ),
    "consultation_purchase": (
        "Consultation Booked",
        lambda d: (
            f"Hi {d.get('first_name', 'there')},\n\n"
            f"Your consultation has been booked for {d.get('date', 'the scheduled time')}.\n\n"
            "We'll be in touch with further details."
        ),
    ),
    "certificate_issued": (
        "Your Certificate is Ready",
        lambda d: (
            f"Hi {d.get('first_name', 'there')},\n\n"
            f"Congratulations! Your certificate for {d.get('course_name', 'your course')} is ready.\n\n"
            "You can download it from your dashboard."
        ),
    ),
    "password_reset": (
        "Password Reset",
        lambda d: (
            f"Hi {d.get('first_name', 'there')},\n\n"
            f"Click the link below to reset your password:\n{d.get('reset_link', '')}\n\n"
            "If you did not request this, ignore this email."
        ),
    ),
}


def _send_fallback_email(to_email, purpose, template_data):
    """Send a plain-text fallback when no SendGrid template is configured or it fails."""
    fallback = _FALLBACK_EMAILS.get(purpose)
    if not fallback:
        logger.error(f"No fallback email defined for purpose: '{purpose}'")
        return False
    subject, body_fn = fallback
    return send_plain_email(to_email, subject, body_fn(template_data or {}))


def send_email(to_email, purpose, template_data=None):
    """
    Send a transactional email for a given purpose.
    Looks up the active SendGrid template ID for that purpose.
    Falls back to a plain-text email if no template is configured or SendGrid rejects it.

    Usage:
        send_email(
            to_email=user.email,
            purpose='welcome',
            template_data={'first_name': 'John'}
        )
    """
    from .models import EmailTemplateConfig

    try:
        config = EmailTemplateConfig.objects.get(purpose=purpose, is_active=True)
    except EmailTemplateConfig.DoesNotExist:
        logger.warning(f"No active template for '{purpose}', sending plain fallback.")
        return _send_fallback_email(to_email, purpose, template_data)

    sg = get_sendgrid_client()
    message = Mail(
        from_email=Email(settings.DEFAULT_FROM_EMAIL, settings.DEFAULT_FROM_NAME),
        to_emails=To(to_email),
    )
    message.template_id = config.sendgrid_template_id
    message.dynamic_template_data = template_data or {}

    try:
        sg.send(message)
        return True
    except Exception as e:
        logger.error(f"SendGrid template failed for '{purpose}' to {to_email}: {e}. Sending plain fallback.")
        return _send_fallback_email(to_email, purpose, template_data)
