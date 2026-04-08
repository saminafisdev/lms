from django.core.management.base import BaseCommand
from accounts.models import User
from config.sendgrid_contacts import add_contact


class Command(BaseCommand):
    help = "Sync subscribed students to SendGrid marketing contacts"

    def handle(self, *args, **kwargs):
        students = User.objects.filter(
            role="student", student_profile__is_subscribed_to_newsletter=True
        ).select_related("student_profile")

        total = students.count()
        self.stdout.write(f"Syncing {total} students to SendGrid...")

        for i, user in enumerate(students, 1):
            add_contact(user)
            self.stdout.write(f"[{i}/{total}] Synced {user.email}")

        self.stdout.write(self.style.SUCCESS("Done."))
