"""Permissoes da API (as mesmas regras das telas, checadas no back-end)."""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .permissoes import pode_operar_os


class PermissaoPorAcao(BasePermission):
    """A view declara `permissoes_por_acao = {"create": "app.codigo", ...}`; acao sem entrada so exige login."""

    def has_permission(self, request, view):
        permissao = getattr(view, "permissoes_por_acao", {}).get(getattr(view, "action", None))
        return permissao is None or request.user.has_perm(permissao)


class EscritaComPermissao(BasePermission):
    """Leitura para qualquer usuario logado; escrita exige `permissao_escrita` da view."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or request.user.has_perm(view.permissao_escrita)


class OperaASuaOS(BasePermission):
    """Alterar uma OS (status, material, comentario, anexo): Coordenacao ou o tecnico dela (evita IDOR/BOLA)."""
    ACOES = {"partial_update", "comentar", "anexar", "materiais"}

    def has_object_permission(self, request, view, obj):
        return view.action not in self.ACOES or pode_operar_os(request.user, obj)
