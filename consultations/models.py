from django.db import models
from accounts.models import TeacherProfile


class Consultation(models.Model):
    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.CASCADE, related_name="consultations"
    )
    day = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    zoom_link = models.URLField(
        blank=True, null=True, help_text="Zoom integration link"
    )

    def __str__(self):
        return (
            f"{self.teacher.user.email} - {self.day} {self.start_time}-{self.end_time}"
        )

    class Meta:
        ordering = ["day", "start_time"]


class Bundle(models.Model):
    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.CASCADE, related_name="consultation_bundles"
    )
    num_sessions = models.PositiveIntegerField(
        help_text="Number of sessions in the bundle"
    )
    original_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Discount percentage (e.g., 10.00 for 10%)",
    )
    final_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Bundle: {self.num_sessions} sessions with {self.teacher.user.email}"
