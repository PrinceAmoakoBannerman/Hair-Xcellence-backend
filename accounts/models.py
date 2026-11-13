from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Extra details for a website customer account (the login itself is Django's User)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=80, blank=True)
    region = models.CharField(max_length=60, blank=True)

    def __str__(self) -> str:
        return f"Profile of {self.user.get_full_name() or self.user.email}"
