"""Paineis: geral, triagem, manutencao e instalacao. So leitura; os numeros saem dos chamados e OSs."""
from collections import Counter
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from chamados.campos import TIPOS
from chamados.models import Chamado, Tipo
from estoque.models import Produto
from ordens.models import OrdemServico

OS_ABERTAS = ["ABERTA", "AGENDADA", "EM_ANDAMENTO", "PENDENTE", "PAUSADA"]
# Mesmas cores das pilulas de status (static/css/erp.css)
CORES_CHAMADO = {"NOVO": "#2563eb", "EM_ATENDIMENTO": "#f59e0b", "PENDENTE_CLIENTE": "#94a3b8",
                 "RESOLVIDO": "#16a34a", "CANCELADO": "#dc2626"}
CORES_OS = {"ABERTA": "#2563eb", "AGENDADA": "#7c3aed", "EM_ANDAMENTO": "#f59e0b", "PENDENTE": "#ea580c",
            "PAUSADA": "#94a3b8", "FECHADA": "#16a34a", "CANCELADA": "#dc2626"}
JANELA = 30   # dias considerados para indicadores de resultado (resolvidos, cumprimento, MTTR)


def _desde(dias=JANELA):
    return timezone.now() - timedelta(days=dias)


def _indicadores(chamados):
    """Situacao do SLA dos abertos + cumprimento e MTTR dos resolvidos no periodo."""
    abertos = list(chamados.exclude(status__in=Chamado.ENCERRADOS).select_related("cliente"))
    situacoes = Counter(c.situacao_sla for c in abertos)
    resolvidos = list(chamados.filter(status=Chamado.Status.RESOLVIDO, resolvido_em__gte=_desde()))
    com_sla = [c for c in resolvidos if c.prazo_solucao]
    duracoes = [c.resolvido_em - c.aberto_em - c.tempo_pausado for c in resolvidos]
    mttr = sum(duracoes, timedelta()) / len(duracoes) if duracoes else None
    return {
        "abertos": len(abertos),
        "estourados": situacoes["ESTOURADO"],
        "em_risco": situacoes["EM_RISCO"],
        "pausados": situacoes["PAUSADO"],
        "resolvidos": len(resolvidos),
        "cumprimento": round(sum(c.situacao_sla == "CUMPRIDO" for c in com_sla) / len(com_sla) * 100)
        if com_sla else None,
        "mttr_horas": round(mttr.total_seconds() / 3600, 1) if mttr else None,
        "fila": sorted(abertos, key=lambda c: (c.prazo_solucao_efetivo is None, c.prazo_solucao_efetivo or 0)),
    }


def _por_status(recentes, choices, cores):
    totais = dict(recentes.values_list("status").annotate(t=Count("id")).order_by())
    itens = [{"codigo": c, "nome": n, "total": totais.get(c, 0), "cor": cores[c]} for c, n in choices]
    return {"itens": itens, "grafico": {"labels": [i["nome"] for i in itens], "valores": [i["total"] for i in itens],
                                        "cores": [i["cor"] for i in itens]}}


def _status_chamados(chamados):
    """Tudo que esta aberto + o que foi resolvido/cancelado nos ultimos 30 dias."""
    recentes = (chamados.exclude(status__in=Chamado.ENCERRADOS) | chamados.filter(resolvido_em__gte=_desde())
                | chamados.filter(status=Chamado.Status.CANCELADO, aberto_em__gte=_desde()))
    return _por_status(recentes, Chamado.Status.choices, CORES_CHAMADO)


def _status_os(ordens):
    recentes = (ordens.filter(status__in=OS_ABERTAS) | ordens.filter(data_fechamento__gte=_desde())
                | ordens.filter(status="CANCELADA", data_abertura__gte=_desde()))
    return _por_status(recentes, OrdemServico.Status.choices, CORES_OS)


def _ranking(chamados, campo, n=5, dias=90):
    """Os n valores que mais aparecem (ex.: ativos ou locais com mais atividades em 90 dias)."""
    return list(chamados.filter(aberto_em__gte=_desde(dias)).exclude(**{campo: ""})
                .values(campo).annotate(total=Count("id")).order_by("-total")[:n])


def _contagem_detalhe(abertos, tipo, nome):
    """Quantos abertos tem cada opcao de um campo especifico (ex.: 'Quem esta afetado')."""
    campo = next(c for c in TIPOS[tipo]["campos"] if c.nome == nome)
    totais = Counter(c.detalhes.get(nome) for c in abertos)
    return [{"nome": rotulo, "total": totais.get(valor, 0)} for valor, rotulo in campo.opcoes]


@login_required
def geral(request):
    """Visao geral de todas as atividades (chamados + OSs) e seus status."""
    chamados = Chamado.objects.all()
    ordens = OrdemServico.objects.all()
    ind = _indicadores(chamados)
    abertos = ind["fila"]
    context = {
        "ind": ind,
        "aguardando_triagem": sum(c.status == Chamado.Status.NOVO for c in abertos),
        "por_tipo": [{"codigo": t, "nome": n, "total": sum(c.tipo == t for c in abertos),
                      "url": f"painel_{t.lower()}"} for t, n in Tipo.choices],
        "status_chamados": _status_chamados(chamados),
        "status_os": _status_os(ordens),
        "os_abertas": ordens.filter(status__in=OS_ABERTAS).count(),
        "fila": abertos[:8],
        "minhas": ordens.filter(status__in=OS_ABERTAS, responsavel=request.user)
                  .select_related("cliente", "chamado").order_by("data_agendada")[:6],
        "alertas": [p for p in Produto.objects.filter(ativo=True) if p.abaixo_do_minimo],
    }
    return render(request, "dashboard/geral.html", context)


@login_required
def triagem(request):
    """Fila de triagem: o que ainda nao teve primeira resposta e o quanto falta para o prazo de resposta."""
    agora = timezone.now()
    novos = list(Chamado.objects.filter(status=Chamado.Status.NOVO).select_related("cliente", "responsavel")
                 .order_by("prazo_resposta"))
    for c in novos:
        c.na_fila = agora - c.aberto_em
        c.resposta_vencida = bool(c.prazo_resposta and agora > c.prazo_resposta)
        c.resposta_vence_logo = bool(c.prazo_resposta and not c.resposta_vencida
                                     and c.prazo_resposta - agora <= timedelta(hours=1))
    respondidos = list(Chamado.objects.filter(primeira_resposta_em__gte=_desde()))
    com_prazo = [c for c in respondidos if c.prazo_resposta]
    tempos = [c.primeira_resposta_em - c.aberto_em for c in respondidos]
    medio = sum(tempos, timedelta()) / len(tempos) if tempos else None
    context = {
        "novos": novos,
        "vencidos": sum(c.resposta_vencida for c in novos),
        "vence_logo": sum(c.resposta_vence_logo for c in novos),
        "sem_responsavel": sum(c.responsavel_id is None for c in novos),
        "resposta_no_prazo": round(sum(c.primeira_resposta_em <= c.prazo_resposta for c in com_prazo)
                                   / len(com_prazo) * 100) if com_prazo else None,
        "tempo_medio_min": round(medio.total_seconds() / 60) if medio else None,
        "pendentes_cliente": Chamado.objects.filter(status=Chamado.Status.PENDENTE_CLIENTE)
                             .select_related("cliente").order_by("pausado_desde")[:8],
    }
    return render(request, "dashboard/triagem.html", context)


@login_required
def manutencao(request):
    chamados = Chamado.objects.filter(tipo=Tipo.MANUTENCAO)
    ind = _indicadores(chamados)
    context = {
        "titulo": "Manutencao", "tipo": Tipo.MANUTENCAO, "icone": "bi-wrench-adjustable", "ind": ind,
        "status_chamados": _status_chamados(chamados),
        "status_os": _status_os(OrdemServico.objects.filter(chamado__tipo=Tipo.MANUTENCAO)),
        "seguranca": sum(c.detalhes.get("risco") == "SEGURANCA" for c in ind["fila"]),
        "afetados": _contagem_detalhe(ind["fila"], Tipo.MANUTENCAO, "afetados"),
        "top_ativos": _ranking(chamados, "ativo"),
        "top_locais": _ranking(chamados, "cliente_final"),
    }
    return render(request, "dashboard/manutencao.html", context)


@login_required
def instalacao(request):
    chamados = Chamado.objects.filter(tipo=Tipo.INSTALACAO)
    ind = _indicadores(chamados)
    hoje = timezone.localdate()
    agenda = (OrdemServico.objects.filter(chamado__tipo=Tipo.INSTALACAO, status__in=OS_ABERTAS,
                                          data_agendada__date__gte=hoje,
                                          data_agendada__date__lte=hoje + timedelta(days=7))
              .select_related("chamado", "cliente", "responsavel").order_by("data_agendada"))
    context = {
        "titulo": "Instalacao", "tipo": Tipo.INSTALACAO, "icone": "bi-router", "ind": ind,
        "status_chamados": _status_chamados(chamados),
        "status_os": _status_os(OrdemServico.objects.filter(chamado__tipo=Tipo.INSTALACAO)),
        "com_pendencia": [c for c in ind["fila"] if c.detalhes.get("prerequisitos") == "PENDENTE"],
        "por_servico": _contagem_detalhe(ind["fila"], Tipo.INSTALACAO, "servico_contratado"),
        "agenda": agenda,
        "sem_os": [c for c in ind["fila"] if not c.ordens.exists()][:8],
    }
    return render(request, "dashboard/instalacao.html", context)
