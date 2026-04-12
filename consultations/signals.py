from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import RecurringAvailability
from .utils import delete_future_unbooked_slots, generate_slots_for_rule


@receiver(post_save, sender=RecurringAvailability)
def on_recurring_rule_saved(sender, instance, created, **kwargs):
    if not created:
        # Rule updated — clear future unbooked slots and regenerate
        delete_future_unbooked_slots(instance)
    generate_slots_for_rule(instance)


@receiver(post_delete, sender=RecurringAvailability)
def on_recurring_rule_deleted(sender, instance, **kwargs):
    delete_future_unbooked_slots(instance)
