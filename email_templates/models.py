from django.db import models


class EmailPurpose(models.TextChoices):
    WELCOME = "welcome", "Welcome Email"
    PASSWORD_RESET = "password_reset", "Password Reset"
    COURSE_PURCHASE = "course_purchase", "Course Purchase Confirmation"
    BUNDLE_PURCHASE = "bundle_purchase", "Bundle Purchase Confirmation"
    CONSULTATION_PURCHASE = "consultation_purchase", "Consultation Purchase Confirmation"
    CONSULTATION_RESCHEDULE_ACCEPTED = "consultation_reschedule_accepted", "Consultation Reschedule Accepted"
    CONSULTATION_RESCHEDULE_DECLINED = "consultation_reschedule_declined", "Consultation Reschedule Declined"
    BOOK_PURCHASE = "book_purchase", "Book Purchase Confirmation"
    BLOG_APPROVED = "blog_approved", "Blog Post Approved"
    BLOG_REJECTED = "blog_rejected", "Blog Post Rejected"
    NEWSLETTER = "newsletter", "Newsletter"
    CERTIFICATE_ISSUED = "certificate_issued", "Certificate Issued"
    CONTACT = "contact", "Contact Form Submission"
    MEMBERSHIP_PURCHASE = "membership_purchase", "Membership Purchase Confirmation"


class EmailTemplateConfig(models.Model):
    """
    Maps a purpose (e.g. welcome email) to a SendGrid template ID.
    Admin selects which SendGrid template to use for each purpose.
    Only one active config per purpose at a time.
    """

    purpose = models.CharField(
        max_length=50,
        choices=EmailPurpose.choices,
        unique=True,
    )
    sendgrid_template_id = models.CharField(
        max_length=100, help_text="SendGrid dynamic template ID (starts with d-)"
    )
    description = models.TextField(
        blank=True, help_text="Optional notes about this template mapping"
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="email_template_configs",
    )

    def __str__(self):
        return f"{self.get_purpose_display()} → {self.sendgrid_template_id}"

    class Meta:
        verbose_name = "Email Template Config"
        verbose_name_plural = "Email Template Configs"
        ordering = ["purpose"]
