from django.utils.text import slugify
import uuid


def generate_unique_slug(model_class, title, instance_pk=None):
    """
    Generate a unique slug for any model.
    Appends a short uuid if the base slug already exists.
    """
    base_slug = slugify(title)
    slug = base_slug
    qs = model_class.objects.filter(slug=slug)

    # Exclude current instance on update
    if instance_pk:
        qs = qs.exclude(pk=instance_pk)

    if qs.exists():
        slug = f"{base_slug}-{str(uuid.uuid4())[:8]}"

    return slug
