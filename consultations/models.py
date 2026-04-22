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


class RecurringAvailability(models.Model):
    WEEKDAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    consultation = models.ForeignKey(
        Consultation, on_delete=models.CASCADE, related_name="recurring_rules"
    )
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    start_time = models.TimeField(help_text="Start of availability window")
    end_time = models.TimeField(help_text="End of availability window")
    session_duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Duration of each individual session slot in minutes",
    )
    valid_from = models.DateField(help_text="First date this rule applies from")
    valid_until = models.DateField(
        null=True, blank=True,
        help_text="Last date this rule applies (leave blank for ongoing)",
    )

    class Meta:
        ordering = ["weekday", "start_time"]
        verbose_name_plural = "Recurring availabilities"

    def __str__(self):
        return (
            f"{self.get_weekday_display()} {self.start_time}–{self.end_time} "
            f"({self.session_duration_minutes}min) — {self.consultation.title}"
        )


class AvailableTimeslot(models.Model):
    consultation = models.ForeignKey(
        Consultation, on_delete=models.CASCADE, related_name="timeslots"
    )
    recurring_rule = models.ForeignKey(
        RecurringAvailability,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_slots",
        help_text="Set if this slot was auto-generated from a recurring rule",
    )
    scheduled_start = models.DateTimeField(help_text="Session start (UTC)")
    scheduled_end = models.DateTimeField(help_text="Session end (UTC)")
    is_booked = models.BooleanField(default=False)

    zoom_meeting_id = models.CharField(max_length=255, blank=True, null=True)
    zoom_join_url = models.URLField(max_length=1000, blank=True, null=True)
    zoom_start_url = models.URLField(max_length=1000, blank=True, null=True)

    def __str__(self):
        return f"{self.consultation.title} - {self.scheduled_start} → {self.scheduled_end}"

    class Meta:
        ordering = ["scheduled_start"]
        indexes = [
            models.Index(fields=["consultation", "is_booked"], name="ts_consult_booked_idx"),
            models.Index(fields=["scheduled_start", "is_booked"], name="ts_start_booked_idx"),
        ]


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

    class Meta:
        indexes = [
            models.Index(fields=["student", "status"], name="purchase_stu_status_idx"),
        ]

    def __str__(self):
        return f"Purchase by {self.student.email} for {self.consultation.title}"


class RescheduleRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    purchase = models.ForeignKey(
        ConsultationPurchase,
        on_delete=models.CASCADE,
        related_name="reschedule_requests",
    )
    old_slot = models.ForeignKey(
        AvailableTimeslot,
        on_delete=models.CASCADE,
        related_name="reschedule_requests_as_old",
    )
    requested_slot = models.ForeignKey(
        AvailableTimeslot,
        on_delete=models.CASCADE,
        related_name="reschedule_requests_as_new",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"RescheduleRequest #{self.pk} [{self.status}] for purchase #{self.purchase_id}"
