from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Profile

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
    fields = ("phone", "address", "city", "region")


admin.site.unregister(User)


@admin.register(User)
class AccountUserAdmin(UserAdmin):
    """Website customers and staff share Django's user table; staff have 'Staff status' ticked."""

    inlines = [ProfileInline]
    list_display = ("email", "first_name", "last_name", "is_staff", "date_joined", "last_login")
    list_filter = ("is_staff", "is_superuser", "is_active", "date_joined")
    search_fields = ("email", "first_name", "last_name", "username")
    ordering = ("-date_joined",)
