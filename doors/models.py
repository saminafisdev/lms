from django.db import models


class Door(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    icon = models.FileField(
        upload_to="doors/icons/",
    )
    is_visible = models.BooleanField(default=True)
    redirect_link = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["-created_at"]
