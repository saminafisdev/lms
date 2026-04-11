from django.db import models
from django.contrib.auth import get_user_model
from accounts.models import TeacherProfile

User = get_user_model()


class Consultation(models.Model):
    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.CASCADE, related_name="consultations"
    )
    title = models.CharField(max_length=255, default="General Consultation")
    description = models.TextField(blank=True, null=True)
    standard_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Standard price per session",
    )

    def __str__(self):
        return f"{self.title} by {self.teacher.user.email}"


class AvailableTimeslot(models.Model):
    consultation = models.ForeignKey(
        Consultation, on_delete=models.CASCADE, related_name="timeslots"
    )
    day = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_booked = models.BooleanField(default=False)

    zoom_meeting_id = models.CharField(max_length=255, blank=True, null=True)
    zoom_join_url = models.URLField(max_length=1000, blank=True, null=True)
    zoom_start_url = models.URLField(max_length=1000, blank=True, null=True)

    def __str__(self):
        return (
            f"{self.consultation.title} - {self.day} {self.start_time}-{self.end_time}"
        )

    class Meta:
        ordering = ["day", "start_time"]


class Bundle(models.Model):
    consultation = models.ForeignKey(
        Consultation, on_delete=models.CASCADE, related_name="bundles"
    )
    num_sessions = models.PositiveIntegerField(
        help_text="The number of sessions a student must purchase to receive a discount"
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Discount percentage applied when conditions are met",
    )

    def __str__(self):
        return f"Bundle: {self.num_sessions} sessions for {self.consultation.title}"


class ConsultationPurchase(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    )

    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="consultation_purchases"
    )
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE)
    bundle_applied = models.ForeignKey(
        Bundle, null=True, blank=True, on_delete=models.SET_NULL
    )

    # Financials
    total_price_paid = models.DecimalField(max_digits=10, decimal_places=2)
    sessions_purchased = models.PositiveIntegerField()

    # Payment
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    payment_reference = models.CharField(max_length=255, blank=True, null=True)

    # The literal times selected
    booked_slots = models.ManyToManyField(AvailableTimeslot, related_name="purchases")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Purchase by {self.student.email} for {self.consultation.title}"
