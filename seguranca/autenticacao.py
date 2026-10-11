"""Token da API com prazo de validade. Modulo separado: o DRF importa isto enquanto carrega as proprias views."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication


def validade():
    return timedelta(hours=settings.API_TOKEN_HORAS)


class TokenComExpiracao(TokenAuthentication):
    """Igual ao token do DRF, mas recusa (e apaga) token mais velho que API_TOKEN_HORAS."""

    def authenticate_credentials(self, key):
        usuario, token = super().authenticate_credentials(key)
        if token.created < timezone.now() - validade():
            token.delete()
            raise exceptions.AuthenticationFailed("Token expirado. Gere um novo em /api/token/.")
        return usuario, token
