"""Delete a photo's file (on Cloudinary, or locally) once it is removed or replaced in the admin."""
import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save

log = logging.getLogger(__name__)


def _delete_file(storage, name: str) -> None:
    from .models import ProductImage
    if not name or ProductImage.objects.filter(image=name).exists():
        return  # still used by another photo
    try:
        storage.delete(name)
    except Exception:  # never block saving because a file couldn't be cleaned up
        log.warning("Could not delete photo file %s", name, exc_info=True)


def remember_old_file(sender, instance, **kwargs):
    instance._old_image_name = ""
    if instance.pk:
        old = sender.objects.filter(pk=instance.pk).values_list("image", flat=True).first()
        instance._old_image_name = old or ""


def delete_replaced_file(sender, instance, created, **kwargs):
    old = getattr(instance, "_old_image_name", "")
    if old and old != (instance.image.name or ""):
        storage = instance.image.storage
        transaction.on_commit(lambda: _delete_file(storage, old))


def delete_removed_file(sender, instance, **kwargs):
    name = instance.image.name if instance.image else ""
    if name:
        storage = instance.image.storage
        transaction.on_commit(lambda: _delete_file(storage, name))


def connect() -> None:
    from .models import ProductImage
    pre_save.connect(remember_old_file, sender=ProductImage, dispatch_uid="photo-remember-old")
    post_save.connect(delete_replaced_file, sender=ProductImage, dispatch_uid="photo-delete-replaced")
    post_delete.connect(delete_removed_file, sender=ProductImage, dispatch_uid="photo-delete-removed")
