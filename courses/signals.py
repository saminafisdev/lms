import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Lesson

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Lesson)
def lesson_pre_save(sender, instance, **kwargs):
    """Snapshot old values so post_save can detect changes."""
    if instance.pk:
        try:
            old = Lesson.objects.get(pk=instance.pk)
            instance._old_content_type = old.content_type
            instance._old_scheduled_at = old.scheduled_at
            instance._old_zoom_meeting_id = old.zoom_meeting_id
        except Lesson.DoesNotExist:
            instance._old_content_type = None
            instance._old_scheduled_at = None
            instance._old_zoom_meeting_id = None
    else:
        instance._old_content_type = None
        instance._old_scheduled_at = None
        instance._old_zoom_meeting_id = None


@receiver(post_save, sender=Lesson)
def lesson_post_save(sender, instance, created, **kwargs):
    from config.zoom import create_meeting, delete_meeting

    is_live = instance.content_type == "live"
    was_live = instance._old_content_type == "live"
    old_meeting_id = getattr(instance, "_old_zoom_meeting_id", None)

    if is_live and instance.scheduled_at:
        # Recreate if: newly live, switched to live, or scheduled_at changed
        should_recreate = (
            not instance.zoom_meeting_id
            or not was_live
            or instance._old_scheduled_at != instance.scheduled_at
        )

        if should_recreate:
            if old_meeting_id and was_live:
                try:
                    delete_meeting(old_meeting_id)
                except Exception as e:
                    logger.warning(f"Could not delete old Zoom meeting {old_meeting_id}: {e}")

            try:
                duration = instance.duration_in_minutes or 60
                result = create_meeting(
                    topic=instance.title,
                    start_datetime=instance.scheduled_at,
                    duration_minutes=duration,
                )
                Lesson.objects.filter(pk=instance.pk).update(
                    zoom_meeting_id=result["meeting_id"],
                    zoom_join_url=result["join_url"],
                    zoom_start_url=result["start_url"],
                )
                logger.info(f"Zoom meeting created for Lesson {instance.pk}: {result['meeting_id']}")
            except Exception as e:
                logger.error(f"Failed to create Zoom meeting for Lesson {instance.pk}: {e}")

    elif was_live and not is_live:
        # Switched away from live — cancel existing meeting
        if old_meeting_id:
            try:
                delete_meeting(old_meeting_id)
            except Exception as e:
                logger.warning(f"Could not delete Zoom meeting {old_meeting_id}: {e}")
            Lesson.objects.filter(pk=instance.pk).update(
                zoom_meeting_id=None,
                zoom_join_url=None,
                zoom_start_url=None,
            )


@receiver(post_delete, sender=Lesson)
def lesson_post_delete(sender, instance, **kwargs):
    if instance.zoom_meeting_id:
        from config.zoom import delete_meeting
        try:
            delete_meeting(instance.zoom_meeting_id)
            logger.info(f"Zoom meeting {instance.zoom_meeting_id} deleted for Lesson {instance.pk}")
        except Exception as e:
            logger.warning(f"Could not delete Zoom meeting {instance.zoom_meeting_id}: {e}")
