import json
import logging
import sendgrid
from django.conf import settings

logger = logging.getLogger(__name__)


def add_contact(user):
    """Add a student to SendGrid marketing contacts."""
    sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
    data = {
        "contacts": [
            {
                "email": user.email,
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
            }
        ]
    }
    try:
        sg.client.marketing.contacts.put(request_body=data)
        logger.info(f"Added {user.email} to SendGrid contacts")
    except Exception as e:
        logger.error(f"SendGrid contact sync failed for {user.email}: {e}")


def remove_contact(user):
    """Remove a student from SendGrid marketing contacts."""
    sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
    try:
        response = sg.client.marketing.contacts.search.emails.post(
            request_body={"emails": [user.email]}
        )
        body = json.loads(response.body)
        contact_id = body["result"][user.email]["contact"]["id"]
        sg.client.marketing.contacts.delete(query_params={"ids": contact_id})
        logger.info(f"Removed {user.email} from SendGrid contacts")
    except Exception as e:
        logger.error(f"SendGrid contact removal failed for {user.email}: {e}")
