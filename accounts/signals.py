from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import CustomUser, TeacherProfile

@receiver(post_save, sender=CustomUser)
def create_teacher_profile(sender, instance, created, **kwargs):
    if created and instance.role == 'teacher':
        TeacherProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=CustomUser)
def save_teacher_profile(sender, instance, **kwargs):
    if instance.role == 'teacher':
        if hasattr(instance, 'teacher_profile'):
            instance.teacher_profile.save()
        else:
            TeacherProfile.objects.get_or_create(user=instance)
