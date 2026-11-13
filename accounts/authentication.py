"""Customer sign-in tokens that expire, so a token copied from an old device stops working."""
from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed


def is_expired(token: Token) -> bool:
    return token.created < timezone.now() - settings.CUSTOMER_TOKEN_TTL


def fresh_token(user) -> Token:
    """The customer's current token, replaced with a new one if it has expired."""
    token, created = Token.objects.get_or_create(user=user)
    if not created and is_expired(token):
        token.delete()
        token = Token.objects.create(user=user)
    return token


class ExpiringTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if is_expired(token):
            token.delete()
            raise AuthenticationFailed("Your session has expired. Please sign in again.")
        return user, token
