from django.db import models
from django.utils import timezone


class MembershipPlan(models.Model):
    """Singleton — admin configures the single membership plan."""

    name = models.CharField(max_length=150, default="Membership")
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField(
        default=30,
        help_text="How many days the membership lasts after payment.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="If disabled, users cannot subscribe.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Membership Plan"
        verbose_name_plural = "Membership Plan"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={"price": 0, "name": "Membership"},
        )
        return obj

    def __str__(self):
        return f"{self.name} ({self.duration_days} days — ${self.price})"


class UserMembership(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        FAILED = "failed", "Failed"

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="membership",
    )
    plan = models.ForeignKey(MembershipPlan, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    payment_reference = models.CharField(max_length=255, blank=True, null=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Membership"
        verbose_name_plural = "User Memberships"
        ordering = ["-created_at"]

    @property
    def is_currently_active(self):
        return (
            self.status == self.Status.ACTIVE
            and self.end_date is not None
            and self.end_date > timezone.now()
        )

    def __str__(self):
        return f"{self.user} — {self.status}"
