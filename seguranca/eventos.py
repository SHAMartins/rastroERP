"""Registro de eventos de seguranca: no banco (tela de log) e no log da aplicacao (stdout do container)."""
import logging
from contextvars import ContextVar

from .models import EventoSeguranca

logger = logging.getLogger("seguranca")
usuario_atual = ContextVar("usuario_atual", default=None)   # preenchido pelo middleware a cada requisicao


def registrar(tipo, usuario=None, nome_usuario="", ip=None, detalhe="", autor=None):
    autor = autor or usuario_atual.get()
    if autor is not None and (not getattr(autor, "is_authenticated", False) or autor == usuario):
        autor = None
    nome = nome_usuario or (usuario.get_username() if usuario else "")
    EventoSeguranca.objects.create(tipo=tipo, usuario=usuario, nome_usuario=nome[:150], ip=ip,
                                   detalhe=detalhe[:255], autor=autor)
    logger.info("%s usuario=%s ip=%s autor=%s %s", tipo, nome, ip or "-", autor or "-", detalhe)
