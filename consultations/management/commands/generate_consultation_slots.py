from django.core.management.base import BaseCommand

from consultations.models import RecurringAvailability
from consultations.utils import generate_slots_for_rule


class Command(BaseCommand):
    help = "Generate upcoming consultation slots for all active recurring rules (run weekly via cron)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--weeks",
            type=int,
            default=8,
            help="How many weeks ahead to generate slots (default: 8)",
        )

    def handle(self, *args, **options):
        weeks = options["weeks"]
        rules = RecurringAvailability.objects.select_related("consultation").all()
        total_created = 0

        for rule in rules:
            created = generate_slots_for_rule(rule, weeks=weeks)
            total_created += created
            if created:
                self.stdout.write(f"  Rule {rule}: {created} new slots")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {total_created} new slots created across {rules.count()} rules."
            )
        )
