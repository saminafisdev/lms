"""
Migration: Replace day/start_time/end_time with scheduled_start/scheduled_end (UTC DateTimeField).

Data migration: combines existing day + start_time / end_time into aware UTC datetimes.
"""
from django.db import migrations, models
from django.utils.timezone import make_aware
from datetime import datetime


def forwards(apps, schema_editor):
    AvailableTimeslot = apps.get_model("consultations", "AvailableTimeslot")
    for slot in AvailableTimeslot.objects.all():
        if slot.day and slot.start_time and slot.end_time:
            slot.scheduled_start = make_aware(datetime.combine(slot.day, slot.start_time))
            slot.scheduled_end = make_aware(datetime.combine(slot.day, slot.end_time))
            slot.save(update_fields=["scheduled_start", "scheduled_end"])


def backwards(apps, schema_editor):
    AvailableTimeslot = apps.get_model("consultations", "AvailableTimeslot")
    for slot in AvailableTimeslot.objects.all():
        if slot.scheduled_start and slot.scheduled_end:
            slot.day = slot.scheduled_start.date()
            slot.start_time = slot.scheduled_start.time()
            slot.end_time = slot.scheduled_end.time()
            slot.save(update_fields=["day", "start_time", "end_time"])


class Migration(migrations.Migration):

    dependencies = [
        ("consultations", "0005_recurringavailability_and_more"),
    ]

    operations = [
        # 1. Add new nullable fields
        migrations.AddField(
            model_name="availabletimeslot",
            name="scheduled_start",
            field=models.DateTimeField(null=True, blank=True, help_text="Session start (UTC)"),
        ),
        migrations.AddField(
            model_name="availabletimeslot",
            name="scheduled_end",
            field=models.DateTimeField(null=True, blank=True, help_text="Session end (UTC)"),
        ),
        # 2. Populate new fields from old ones
        migrations.RunPython(forwards, backwards),
        # 3. Make new fields non-nullable
        migrations.AlterField(
            model_name="availabletimeslot",
            name="scheduled_start",
            field=models.DateTimeField(help_text="Session start (UTC)"),
        ),
        migrations.AlterField(
            model_name="availabletimeslot",
            name="scheduled_end",
            field=models.DateTimeField(help_text="Session end (UTC)"),
        ),
        # 4. Remove old index before removing the column it references
        migrations.RemoveIndex(model_name="availabletimeslot", name="ts_day_booked_idx"),
        # 5. Remove old fields
        migrations.RemoveField(model_name="availabletimeslot", name="day"),
        migrations.RemoveField(model_name="availabletimeslot", name="start_time"),
        migrations.RemoveField(model_name="availabletimeslot", name="end_time"),
        # 6. Add new index on scheduled_start
        migrations.AddIndex(
            model_name="availabletimeslot",
            index=models.Index(
                fields=["scheduled_start", "is_booked"],
                name="ts_start_booked_idx",
            ),
        ),
        # 6. Update ordering (handled by Meta, but we update the model state)
        migrations.AlterModelOptions(
            name="availabletimeslot",
            options={"ordering": ["scheduled_start"]},
        ),
    ]
