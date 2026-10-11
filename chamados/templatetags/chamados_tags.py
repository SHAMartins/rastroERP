from django import template
from django.utils import timezone
from django.utils.html import format_html

register = template.Library()

SITUACOES = {
    "NO_PRAZO": ("No prazo", "bi-check-circle"),
    "EM_RISCO": ("Em risco", "bi-exclamation-circle"),
    "ESTOURADO": ("Estourado", "bi-x-octagon"),
    "PAUSADO": ("Pausado", "bi-pause-circle"),
    "CUMPRIDO": ("Cumprido", "bi-check2-all"),
    "VIOLADO": ("Violado", "bi-x-circle"),
    "SEM_SLA": ("Sem SLA", "bi-dash-circle"),
}
ICONES_TIPO = {"MANUTENCAO": "bi-wrench-adjustable", "INSTALACAO": "bi-router"}


def _duracao(segundos):
    minutos = int(abs(segundos) // 60)
    dias, resto = divmod(minutos, 1440)
    horas, mins = divmod(resto, 60)
    if dias:
        return f"{dias}d {horas}h"
    if horas:
        return f"{horas}h {mins:02d}min"
    return f"{mins}min"


@register.simple_tag
def sla_badge(chamado):
    rotulo, icone = SITUACOES[chamado.situacao_sla]
    return format_html('<span class="pilula sla-{}"><i class="bi {}"></i>{}</span>', chamado.situacao_sla, icone, rotulo)


@register.simple_tag
def sla_restante(chamado):
    """'faltam 3h 20min' ou 'estourou ha 2h' (texto curto para listas)."""
    situacao = chamado.situacao_sla
    if situacao in ("SEM_SLA", "CUMPRIDO", "VIOLADO"):
        return ""
    if situacao == "PAUSADO":
        return "relogio parado"
    segundos = (chamado.prazo_solucao_efetivo - timezone.now()).total_seconds()
    return f"faltam {_duracao(segundos)}" if segundos >= 0 else f"estourou ha {_duracao(segundos)}"


@register.simple_tag
def tipo_badge(chamado):
    return format_html('<span class="pilula tp-{}"><i class="bi {}"></i>{}</span>',
                       chamado.tipo, ICONES_TIPO.get(chamado.tipo, "bi-tag"), chamado.get_tipo_display())


@register.filter
def icone_tipo(tipo):
    return ICONES_TIPO.get(tipo, "bi-tag")


@register.filter
def duracao(td):
    return _duracao(td.total_seconds()) if td else "0min"
