from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Profile

User = get_user_model()


def full_name(user) -> str:
    return " ".join(p for p in [user.first_name, user.last_name] if p).strip()


class AccountSerializer(serializers.Serializer):
    """What the website sees about the signed-in customer."""

    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(read_only=True)
    phone = serializers.CharField(max_length=30, allow_blank=True, required=False)
    address = serializers.CharField(max_length=255, allow_blank=True, required=False)
    city = serializers.CharField(max_length=80, allow_blank=True, required=False)
    region = serializers.CharField(max_length=60, allow_blank=True, required=False)
    date_joined = serializers.DateTimeField(read_only=True)

    def to_representation(self, user):
        profile, _ = Profile.objects.get_or_create(user=user)
        return {
            "name": full_name(user), "email": user.email, "date_joined": user.date_joined,
            "phone": profile.phone, "address": profile.address, "city": profile.city, "region": profile.region,
        }

    def update(self, user, data):
        if "name" in data:
            first, _, last = data["name"].strip().partition(" ")
            user.first_name, user.last_name = first[:150], last.strip()[:150]
            user.save(update_fields=["first_name", "last_name"])
        profile, _ = Profile.objects.get_or_create(user=user)
        for field in ("phone", "address", "city", "region"):
            if field in data:
                setattr(profile, field, data[field])
        profile.save()
        return user


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, max_length=128, style={"input_type": "password"})

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(username__iexact=value).exists() or User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists. Try signing in.")
        return value

    def validate(self, data):
        try:
            validate_password(data["password"], user=User(username=data["email"], email=data["email"], first_name=data["name"]))
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return data

    def create(self, data):
        first, _, last = data["name"].strip().partition(" ")
        user = User.objects.create_user(
            username=data["email"], email=data["email"], password=data["password"],
            first_name=first[:150], last_name=last.strip()[:150],
        )
        Profile.objects.create(user=user)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, data):
        user = authenticate(username=data["email"].strip().lower(), password=data["password"])
        if not user or not user.is_active:
            raise serializers.ValidationError("Email or password is incorrect.")
        data["user"] = user
        return data
