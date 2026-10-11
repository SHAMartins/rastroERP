from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from . import bloqueio


class BackendComBloqueio(ModelBackend):
    """Autenticacao padrao do Django + bloqueio por excesso de tentativas.

    Fica no backend para valer em todas as entradas: tela de login, admin e token da API.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username and bloqueio.bloqueado(username, bloqueio.ip_do_request(request)):
            raise PermissionDenied("Muitas tentativas de login.")   # nem chega a testar a senha
        return super().authenticate(request, username=username, password=password, **kwargs)
