from django.db import models
from django.conf import settings
from django_resized import ResizedImageField

from courses.models import Course


class CourseAnnouncement(models.Model):
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="announcements"
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="course_announcements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.course}] {self.title}"


class SiteAnnouncement(models.Model):
    title_prefix = models.CharField(max_length=100, blank=True, default="")
    main_title = models.CharField(max_length=255)
    message = models.TextField(blank=True, default="")
    badges = models.JSONField(default=list, blank=True, help_text="List of campaign badge strings, e.g. ['New', 'Limited']")
    image = ResizedImageField(
        size=[800, 600],
        upload_to="announcements/",
        blank=True,
        null=True,
    )
    cta_text = models.CharField(max_length=100, blank=True, default="")
    cta_link = models.URLField(blank=True, default="")
    highlights = models.JSONField(default=list, blank=True, help_text="List of highlight strings, e.g. ['Free shipping', '24/7 support']")
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Ensure only one site announcement is active at a time
        if self.is_active:
            SiteAnnouncement.objects.exclude(pk=self.pk).filter(is_active=True).update(
                is_active=False
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.main_title
