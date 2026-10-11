"""Checagens de autorizacao feitas no back-end (esconder botao no front-end nao basta)."""
from django.core.exceptions import PermissionDenied


def exigir(usuario, permissao, mensagem="Seu perfil nao permite esta acao."):
    if not usuario.has_perm(permissao):
        raise PermissionDenied(mensagem)


def pode_operar_os(usuario, ordem):
    """Coordenacao/Administrador operam qualquer OS; o tecnico, so as atribuidas a ele (evita IDOR)."""
    if usuario.has_perm("ordens.operar_qualquer_os"):
        return True
    return ordem.responsavel_id is not None and ordem.responsavel_id == usuario.pk


def exigir_operar_os(usuario, ordem):
    if not pode_operar_os(usuario, ordem):
        raise PermissionDenied(f"A OS {ordem.numero} nao esta atribuida a voce.")
