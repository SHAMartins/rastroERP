"""Limite de tentativas de login (protecao contra forca bruta).

Conta falhas por usuario e por IP numa janela de tempo. Ao passar do limite, bloqueia novas
tentativas por um periodo, mesmo com a senha certa. Os contadores ficam no cache do Django.
"""
from django.conf import settings
from django.core.cache import cache

JANELA = settings.LOGIN_JANELA_MINUTOS * 60
BLOQUEIO = settings.LOGIN_BLOQUEIO_MINUTOS * 60


def ip_do_request(request):
    if request is None:
        return None
    if settings.CONFIAR_X_FORWARDED_FOR:          # so atras do proxy HTTPS (que reescreve o cabecalho)
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if encaminhado:
            return encaminhado.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _norm(usuario):
    return (usuario or "").strip().lower()


def bloqueado(usuario, ip):
    return bool(cache.get(f"login:bloq:u:{_norm(usuario)}") or (ip and cache.get(f"login:bloq:ip:{ip}")))


def _contar(chave_falhas, chave_bloqueio, limite):
    cache.add(chave_falhas, 0, JANELA)
    try:
        falhas = cache.incr(chave_falhas)
    except ValueError:              # expirou entre o add e o incr
        cache.set(chave_falhas, 1, JANELA)
        falhas = 1
    if falhas >= limite:
        cache.set(chave_bloqueio, True, BLOQUEIO)
        return True
    return False


def registrar_falha(usuario, ip):
    """Devolve True se esta falha causou o bloqueio."""
    bloqueou = _contar(f"login:falhas:u:{_norm(usuario)}", f"login:bloq:u:{_norm(usuario)}",
                       settings.LOGIN_MAX_FALHAS_USUARIO)
    if ip:
        bloqueou = _contar(f"login:falhas:ip:{ip}", f"login:bloq:ip:{ip}", settings.LOGIN_MAX_FALHAS_IP) or bloqueou
    return bloqueou


def limpar(usuario):
    cache.delete_many([f"login:falhas:u:{_norm(usuario)}", f"login:bloq:u:{_norm(usuario)}"])
