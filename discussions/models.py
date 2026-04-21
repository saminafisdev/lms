from django.db import models
from django.conf import settings


class Post(models.Model):
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="discussion_posts",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discussion_posts",
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_pinned = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return f"[{self.course.title}] {self.title}"


class Reply(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discussion_replies",
    )
    body = models.TextField()
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Reply by {self.author.email} on '{self.post.title}'"
