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
