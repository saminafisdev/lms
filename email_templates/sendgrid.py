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


def send_email(to_email, purpose, template_data=None):
    """
    Send a transactional email for a given purpose.
    Looks up the active SendGrid template ID for that purpose.

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
        logger.error(f"No active email template configured for purpose: '{purpose}'")
        return False

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
        logger.error(f"SendGrid failed sending '{purpose}' to {to_email}: {e}")
        return False
