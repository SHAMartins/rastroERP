"""Indicadores ao longo do tempo e por tecnico (apoio a decisao). So leitura."""
from datetime import datetime, time, timedelta

from django.utils import timezone

from chamados.models import Chamado, HistoricoChamado
from ordens.models import OrdemServico

OS_ABERTAS = ["ABERTA", "AGENDADA", "EM_ANDAMENTO", "PENDENTE", "PAUSADA"]


def _horas(td):
    return round(td.total_seconds() / 3600, 1)


def _media(duracoes):
    return sum(duracoes, timedelta()) / len(duracoes) if duracoes else None


def _inicio_do_dia(dia):
    return timezone.make_aware(datetime.combine(dia, time.min))


def evolucao_semanal(chamados, semanas=12):
    """Uma linha por semana (segunda a domingo), da mais antiga para a atual.

    abertas: atividades abertas na semana; resolvidas: resolvidas na semana;
    backlog: em aberto no fim da semana; mttr_h: tempo medio de resolucao (sem o tempo pendente cliente);
    sla_pct: % das resolvidas na semana que cumpriram o prazo de solucao.
    """
    hoje = timezone.localdate()
    primeira = hoje - timedelta(days=hoje.weekday()) - timedelta(weeks=semanas - 1)
    lista = list(chamados)
    # Atividade cancelada nao guarda a data do cancelamento no proprio registro: ela vem do historico
    cancelado = Chamado.Status.CANCELADO.label
    canceladas = {h.chamado_id: h.alterado_em for h in HistoricoChamado.objects.filter(
        chamado__in=[c.pk for c in lista if c.status == Chamado.Status.CANCELADO],
        campo="status", valor_novo=cancelado).order_by("alterado_em")}

    def encerrada_antes(c, limite):
        if c.resolvido_em and c.resolvido_em < limite:
            return True
        quando = canceladas.get(c.pk, c.aberto_em) if c.status == Chamado.Status.CANCELADO else None
        return quando is not None and quando < limite

    linhas = []
    for i in range(semanas):
        inicio = _inicio_do_dia(primeira + timedelta(weeks=i))
        fim = inicio + timedelta(weeks=1)
        resolvidas = [c for c in lista if c.status == Chamado.Status.RESOLVIDO and inicio <= c.resolvido_em < fim]
        com_prazo = [c for c in resolvidas if c.prazo_solucao]
        mttr = _media([c.resolvido_em - c.aberto_em - c.tempo_pausado for c in resolvidas])
        linhas.append({
            "inicio": inicio.date(),
            "rotulo": f"{inicio:%d/%m}",
            "abertas": sum(inicio <= c.aberto_em < fim for c in lista),
            "resolvidas": len(resolvidas),
            "backlog": sum(c.aberto_em < fim and not encerrada_antes(c, fim) for c in lista),
            "mttr_h": _horas(mttr) if mttr else None,
            "sla_pct": round(sum(c.situacao_sla == "CUMPRIDO" for c in com_prazo) / len(com_prazo) * 100)
            if com_prazo else None,
        })
    return linhas


def graficos_evolucao(linhas):
    """Dados no formato do static/js/graficos.js (graficoCombinado)."""
    rotulos = [linha["rotulo"] for linha in linhas]
    return {
        "volume": {"labels": rotulos, "series": [
            {"nome": "Abertas", "tipo": "bar", "cor": "#0e5a6b", "valores": [linha["abertas"] for linha in linhas]},
            {"nome": "Resolvidas", "tipo": "bar", "cor": "#2e7d4f", "valores": [linha["resolvidas"] for linha in linhas]},
            {"nome": "Backlog (em aberto)", "tipo": "line", "cor": "#b26a00",
             "valores": [linha["backlog"] for linha in linhas]},
        ]},
        "qualidade": {"labels": rotulos, "eixo_porcentagem": True, "series": [
            {"nome": "MTTR (horas)", "tipo": "line", "cor": "#5b4b8a", "valores": [linha["mttr_h"] for linha in linhas]},
            {"nome": "SLA cumprido (%)", "tipo": "line", "cor": "#2e7d4f", "eixo": "porcentagem",
             "valores": [linha["sla_pct"] for linha in linhas]},
        ]},
    }


def desempenho_tecnicos(ordens, dias=30):
    """Carga e resultado de cada tecnico: OSs em aberto, atrasadas, concluidas no periodo e tempo medio."""
    agora = timezone.now()
    desde = agora - timedelta(days=dias)
    por_tecnico = {}
    for o in ordens.select_related("responsavel"):
        if o.responsavel is None:
            continue
        t = por_tecnico.setdefault(o.responsavel_id, {"tecnico": o.responsavel, "em_aberto": 0, "atrasadas": 0,
                                                       "concluidas": 0, "_duracoes": []})
        if o.status in OS_ABERTAS:
            t["em_aberto"] += 1
            if o.data_agendada and o.data_agendada < agora:
                t["atrasadas"] += 1
        elif o.status == OrdemServico.Status.FECHADA and o.data_fechamento and o.data_fechamento >= desde:
            t["concluidas"] += 1
            t["_duracoes"].append(o.data_fechamento - o.data_abertura)
    linhas = []
    for t in por_tecnico.values():
        media = _media(t.pop("_duracoes"))
        t["tempo_medio_h"] = _horas(media) if media else None
        linhas.append(t)
    return sorted(linhas, key=lambda t: (-t["em_aberto"], -t["atrasadas"], t["tecnico"].get_username()))


def os_sem_tecnico(ordens):
    return ordens.filter(status__in=OS_ABERTAS, responsavel__isnull=True).count()
