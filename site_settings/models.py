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
        from django.core.cache import cache
        cache.delete('site_settings')

    @classmethod
    def get(cls):
        from django.core.cache import cache
        cached = cache.get('site_settings')
        if cached is None:
            cached, _ = cls.objects.get_or_create(pk=1)
            cache.set('site_settings', cached, 60 * 60 * 6)  # 6 hours
        return cached

    def __str__(self):
        return "Site Settings"


class Testimonial(models.Model):
    name = models.CharField(max_length=150)
    picture = models.ImageField(upload_to="testimonials/", blank=True, null=True)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0, help_text="Controls display order (lower = first).")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "Testimonial"
        verbose_name_plural = "Testimonials"

    def __str__(self):
        return self.name

