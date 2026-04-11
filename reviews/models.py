from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

User = None  # resolved lazily via settings.AUTH_USER_MODEL


class Review(models.Model):
    REVIEW_TYPE_CHOICES = (
        ("course", "Course"),
        ("book", "Book"),
        ("consultation", "Consultation"),
    )

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="reviews"
    )
    review_type = models.CharField(max_length=20, choices=REVIEW_TYPE_CHOICES)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Only one will be set per review
    course = models.ForeignKey(
        "courses.Course",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    book = models.ForeignKey(
        "books.Book",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    consultation = models.ForeignKey(
        "consultations.Consultation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "course"],
                condition=models.Q(course__isnull=False),
                name="unique_review_per_user_course",
            ),
            models.UniqueConstraint(
                fields=["user", "book"],
                condition=models.Q(book__isnull=False),
                name="unique_review_per_user_book",
            ),
            models.UniqueConstraint(
                fields=["user", "consultation"],
                condition=models.Q(consultation__isnull=False),
                name="unique_review_per_user_consultation",
            ),
        ]

    def __str__(self):
        target = self.course or self.book or self.consultation
        return f"{self.user.email} — {self.review_type} — {self.rating}★"
