import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, to_email, purpose, template_data=None):
    """Send a transactional email via SendGrid asynchronously."""
    try:
        from email_templates.sendgrid import send_email, send_plain_email
        sent = send_email(to_email=to_email, purpose=purpose, template_data=template_data or {})
        if not sent:
            logger.warning(f"send_email returned False for {to_email} / {purpose}")
        return sent
    except Exception as exc:
        logger.error(f"Email task failed for {to_email}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def create_zoom_meeting_for_slot_task(self, slot_id, consultation_title, student_name):
    """Create a Zoom meeting for a consultation slot asynchronously."""
    try:
        from config.zoom import create_meeting
        from consultations.models import AvailableTimeslot
        slot = AvailableTimeslot.objects.get(pk=slot_id)
        duration = max(int((slot.scheduled_end - slot.scheduled_start).seconds / 60), 30)
        result = create_meeting(
            topic=f"Consultation: {consultation_title}",
            start_datetime=slot.scheduled_start,
            duration_minutes=duration,
            agenda=f"Session with {student_name}",
        )
        AvailableTimeslot.objects.filter(pk=slot_id).update(
            zoom_meeting_id=result["meeting_id"],
            zoom_join_url=result["join_url"],
            zoom_start_url=result["start_url"],
        )
        logger.info(f"Zoom meeting created for slot {slot_id}: {result['meeting_id']}")
        return result["meeting_id"]
    except Exception as exc:
        logger.error(f"Zoom task failed for slot {slot_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def delete_bunny_video_task(self, video_id):
    """Delete a video from Bunny Stream asynchronously."""
    try:
        from config.bunny_stream import delete_video
        result = delete_video(video_id)
        logger.info(f"Deleted Bunny video {video_id}: {result}")
        return result
    except Exception as exc:
        logger.error(f"Failed to delete Bunny video {video_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def sync_newsletter_contact_task(self, email, action, first_name="", last_name=""):
    """
    Sync a newsletter subscriber with SendGrid Marketing Contacts.
    action: 'subscribe' or 'unsubscribe'
    """
    try:
        from email_templates.sendgrid import add_contact_to_newsletter, remove_contact_from_newsletter
        if action == "subscribe":
            add_contact_to_newsletter(email, first_name=first_name, last_name=last_name)
        elif action == "unsubscribe":
            remove_contact_from_newsletter(email)
    except Exception as exc:
        logger.error(f"Newsletter sync failed for {email} ({action}): {exc}")
        raise self.retry(exc=exc)



@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def create_lulu_print_job_task(self, order_item_id):
    """
    Create a Lulu print job for a physical book OrderItem after payment.
    Uses the book's digital_file URL as the interior PDF for Lulu.
    Saves the returned print_job_id back to the OrderItem.
    """
    try:
        from orders.models import OrderItem
        from orders.lulu import create_print_job

        item = OrderItem.objects.select_related(
            "order__user", "order__shipping_address", "book"
        ).get(id=order_item_id)

        book = item.book
        order = item.order
        address = order.shipping_address

        if not book.lulu_pod_package_id:
            logger.warning(
                "Book %s has no lulu_pod_package_id — skipping Lulu print job for OrderItem %s",
                book.id, item.id,
            )
            return None

        if not book.digital_file:
            logger.warning(
                "Book %s has no digital_file (interior PDF) — skipping Lulu print job for OrderItem %s",
                book.id, item.id,
            )
            return None

        interior_pdf_url = book.digital_file.url

        shipping = {
            "name": address.full_name,
            "street1": address.address_line,
            "city": address.city,
            "country_code": address.country,
            "phone_number": address.phone,
            "email": order.user.email,
        }
        if address.postal_code:
            shipping["postcode"] = address.postal_code

        result = create_print_job(
            title=book.title,
            interior_pdf_url=interior_pdf_url,
            cover_image_url=book.cover_image.url if book.cover_image else "",
            pod_package_id=book.lulu_pod_package_id,
            quantity=item.quantity,
            contact_email=order.user.email,
            shipping_address=shipping,
        )

        item.lulu_print_job_id = str(result["id"])
        item.save(update_fields=["lulu_print_job_id"])
        logger.info(
            "Lulu print job %s created for OrderItem %s (book: %s)",
            result["id"], item.id, book.title,
        )
        return result["id"]

    except Exception as exc:
        logger.error("Lulu print job task failed for OrderItem %s: %s", order_item_id, exc)
        raise self.retry(exc=exc)
