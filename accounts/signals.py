from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, TeacherProfile, StudentProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.role == User.TEACHER:
            TeacherProfile.objects.get_or_create(user=instance)
        elif instance.role == User.STUDENT:
            StudentProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if instance.role == User.TEACHER:
        if hasattr(instance, "teacher_profile"):
            instance.teacher_profile.save()
    elif instance.role == User.STUDENT:
        if hasattr(instance, "student_profile"):
            instance.student_profile.save()
