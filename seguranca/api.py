"""Emissao do token da API, protegida contra forca bruta (o token expira: ver autenticacao.py)."""
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from . import bloqueio
from .autenticacao import validade
from .eventos import registrar
from .models import EventoSeguranca


class ObterToken(ObtainAuthToken):
    """Troca usuario e senha por um token novo (o anterior e invalidado). Limite de tentativas por minuto."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(responses=inline_serializer("TokenEmitido", {
        "token": serializers.CharField(), "expira_em": serializers.DateTimeField()}))
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)          # authenticate(): vale o bloqueio por tentativas
        usuario = serializer.validated_data["user"]
        Token.objects.filter(user=usuario).delete()          # rotacao: um token valido por usuario
        token = Token.objects.create(user=usuario)
        registrar(EventoSeguranca.Tipo.TOKEN_EMITIDO, usuario, ip=bloqueio.ip_do_request(request))
        return Response({"token": token.key, "expira_em": token.created + validade()})
