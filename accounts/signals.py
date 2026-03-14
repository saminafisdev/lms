from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, TeacherProfile, StudentProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.role == User.TEACHER:
            TeacherProfile.objects.create(user=instance)
        elif instance.role == User.STUDENT:
            StudentProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if instance.role == User.TEACHER:
        if not hasattr(instance, "teacher_profile"):
            TeacherProfile.objects.create(user=instance)
        instance.teacher_profile.save()
    elif instance.role == User.STUDENT:
        if not hasattr(instance, "student_profile"):
            StudentProfile.objects.create(user=instance)
        instance.student_profile.save()
