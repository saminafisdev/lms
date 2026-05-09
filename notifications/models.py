from django.db import models
from django.conf import settings


class NotificationType(models.TextChoices):
    ANNOUNCEMENT = "announcement", "Announcement"
    DISCUSSION_REPLY = "discussion_reply", "Discussion Reply"
    ASSIGNMENT_GRADED = "assignment_graded", "Assignment Graded"
    ENROLLMENT = "enrollment", "Enrollment"
    GENERAL = "general", "General"


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
    )
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True, default="")
    link = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Frontend URL to navigate to on click",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.notification_type}] {self.title} → {self.recipient}"
