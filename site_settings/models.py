from django.db import models
from config.validators import sanitize_html


class SiteSettings(models.Model):
    """Singleton model for site-wide settings managed by the admin."""

    # About
    short_about = models.TextField(blank=True)
    long_about = models.TextField(blank=True, help_text="Supports rich HTML content.")

    # Legal pages
    privacy_policy = models.TextField(blank=True, help_text="Supports rich HTML content.")
    terms_and_conditions = models.TextField(blank=True, help_text="Supports rich HTML content.")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        for field in ("long_about", "privacy_policy", "terms_and_conditions"):
            value = getattr(self, field, "")
            if value:
                setattr(self, field, sanitize_html(value))
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Site Settings"
