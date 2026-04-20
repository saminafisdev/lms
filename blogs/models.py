from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django_resized import ResizedImageField
from taggit.managers import TaggableManager
import re

from accounts.models import TeacherProfile

class BlogCategory(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Blog Categories"
        ordering = ["name"]


class Blog(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PENDING = "pending"
    STATUS_PUBLISHED = "published"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING, "Pending Approval"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_REJECTED, "Rejected"),
    )

    author = models.ForeignKey(
        TeacherProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name="blogs",
    )
    category = models.ForeignKey(
        BlogCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blogs",
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True, max_length=300)
    cover_image = ResizedImageField(
        size=[1200, 630],
        crop=["middle", "center"],
        quality=90,
        upload_to="blogs/covers/",
        force_format="WEBP",
        blank=True,
        null=True,
    )
    excerpt = models.CharField(max_length=500, blank=True)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    rejection_reason = models.TextField(blank=True, null=True)
    view_count = models.PositiveIntegerField(default=0)
    tags = TaggableManager(blank=True)
    published_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            from config.utils import generate_unique_slug
            self.slug = generate_unique_slug(Blog, self.title, instance_pk=self.pk)
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def reading_time(self):
        plain_text = re.sub(r"<[^>]+>", "", self.content)
        word_count = len(plain_text.split())
        return max(1, round(word_count / 200))

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["-created_at"]