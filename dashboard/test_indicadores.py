"""Evolucao semanal, desempenho por tecnico e relatorios em planilha (CSV)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from chamados import services as chamados
from chamados.models import Chamado
from config.planilha import celula
from estoque import services as estoque
from estoque.models import Produto
from ordens import services as ordens

from .indicadores import desempenho_tecnicos, evolucao_semanal

pytestmark = pytest.mark.django_db
DADOS = dict(tipo="MANUTENCAO", titulo="Link", solicitante_nome="Ana", endereco="Rua A", ativo="C1",
             impacto="MEDIO", urgencia="MEDIA", detalhes={"sintoma": "x", "afetados": "USUARIO"})


def segunda(semanas_atras):
    """Meio-dia da segunda-feira de N semanas atras (0 = semana atual)."""
    hoje = timezone.localdate()
    dia = hoje - timedelta(days=hoje.weekday()) - timedelta(weeks=semanas_atras)
    return timezone.make_aware(timezone.datetime(dia.year, dia.month, dia.day, 12))


def atividade(usuario, cliente, aberta, resolvida=None, pausada=timedelta()):
    c = chamados.abrir_chamado(usuario, cliente=cliente, **DADOS)
    campos = {"aberto_em": aberta, "prazo_solucao": aberta + timedelta(hours=24), "tempo_pausado": pausada}
    if resolvida:
        campos.update(status="RESOLVIDO", resolvido_em=resolvida)
    Chamado.objects.filter(pk=c.pk).update(**campos)
    return c


def test_evolucao_conta_abertas_resolvidas_e_backlog_por_semana(usuario, cliente):
    atividade(usuario, cliente, segunda(3), resolvida=segunda(2))
    atividade(usuario, cliente, segunda(2))
    atividade(usuario, cliente, segunda(0))
    linhas = evolucao_semanal(Chamado.objects.all(), semanas=4)
    assert [l["abertas"] for l in linhas] == [1, 1, 0, 1]
    assert [l["resolvidas"] for l in linhas] == [0, 1, 0, 0]
    assert [l["backlog"] for l in linhas] == [1, 1, 1, 2]


def test_mttr_desconta_pendente_cliente_e_sla_cumprido(usuario, cliente):
    # 10h de duracao com 4h pendente cliente = 6h; prazo de 24h -> cumprido
    atividade(usuario, cliente, segunda(1), resolvida=segunda(1) + timedelta(hours=10), pausada=timedelta(hours=4))
    # 30h de duracao, prazo de 24h -> violado
    atividade(usuario, cliente, segunda(1), resolvida=segunda(1) + timedelta(hours=30))
    semana = evolucao_semanal(Chamado.objects.all(), semanas=2)[0]
    assert semana["mttr_h"] == 18.0 and semana["sla_pct"] == 50


def test_cancelada_sai_do_backlog_na_semana_do_cancelamento(usuario, cliente):
    c = atividade(usuario, cliente, segunda(2))
    chamados.atualizar_chamado(c, usuario, status="CANCELADO")         # cancelada agora (semana atual)
    linhas = evolucao_semanal(Chamado.objects.all(), semanas=3)
    assert [l["backlog"] for l in linhas] == [1, 1, 0]


def test_desempenho_por_tecnico(usuario, chamado, com_perfil):
    joao = com_perfil("Técnico", "joao")
    atrasada = chamados.gerar_os(chamado, usuario, responsavel=joao, data_agendada=timezone.now() - timedelta(hours=2))
    concluida = chamados.gerar_os(chamado, usuario, responsavel=joao)
    ordens.atualizar_os(concluida, usuario, status="FECHADA")
    chamados.gerar_os(chamado, usuario)                                # sem tecnico: fica fora da tabela
    (linha,) = desempenho_tecnicos(atrasada.__class__.objects.all())
    assert linha["tecnico"] == joao
    assert (linha["em_aberto"], linha["atrasadas"], linha["concluidas"]) == (1, 1, 1)
    assert linha["tempo_medio_h"] is not None


def test_quadro_por_tecnico_so_para_coordenacao(client, com_perfil, ordem):
    client.force_login(com_perfil("Técnico"))
    assert "Ordens de serviço por técnico" not in client.get("/").content.decode()
    assert client.get("/paineis/tecnicos.csv").status_code == 403
    client.force_login(com_perfil("Coordenação"))
    assert "Ordens de serviço por técnico" in client.get("/").content.decode()
    assert client.get("/paineis/tecnicos.csv").status_code == 200


def test_paineis_mostram_evolucao(logado, chamado):
    for url in ["/", "/paineis/manutencao/", "/paineis/instalacao/"]:
        html = logado.get(url).content.decode()
        assert "Evolução nas últimas 12 semanas" in html and 'data-grafico-tipo="combinado"' in html, url


# ---------- Planilhas ----------

def linhas_csv(resposta):
    texto = resposta.content.decode("utf-8")
    assert texto.startswith("﻿")                                     # BOM: Excel le os acentos
    return [linha.split(";") for linha in texto.lstrip("﻿").strip().splitlines()]


def test_planilha_de_atividades_respeita_os_filtros(logado, usuario, cliente, chamado):
    chamados.abrir_chamado(usuario, cliente=cliente, **{**DADOS, "tipo": "INSTALACAO", "ativo": "",
                                                       "detalhes": {"servico_contratado": "VOIP", "escopo": "x",
                                                                    "prerequisitos": "OK"}})
    r = logado.get("/atividades/exportar/?tipo=MANUTENCAO")
    assert r["Content-Type"].startswith("text/csv") and "attachment" in r["Content-Disposition"]
    cabecalho, *linhas = linhas_csv(r)
    assert cabecalho[0] == "Número" and len(linhas) == 1 and linhas[0][0] == chamado.numero


def test_planilha_neutraliza_formula_injetada(logado, usuario, cliente):
    chamados.abrir_chamado(usuario, cliente=cliente, **{**DADOS, "titulo": "=HYPERLINK(\"http://x\",\"clique\")"})
    titulo = linhas_csv(logado.get("/atividades/exportar/"))[1][6]
    assert titulo.startswith("\"'=HYPERLINK") or titulo.startswith("'=HYPERLINK")
    assert celula(-3) == "-3" and celula(2.5) == "2,5"                    # numeros negativos continuam numeros


def test_planilha_de_movimentacoes_e_de_evolucao(logado, usuario):
    produto = Produto.objects.create(codigo="P1", nome="Cabo")
    estoque.registrar_entrada(produto, 5, usuario, "NF 9")
    cabecalho, linha = linhas_csv(logado.get("/estoque/movimentacoes/exportar/"))
    assert cabecalho[1] == "Código" and linha[1] == "P1" and linha[4] == "5"
    evolucao = linhas_csv(logado.get("/paineis/evolucao.csv?tipo=MANUTENCAO"))
    assert evolucao[0][0] == "Semana (início)" and len(evolucao) == 13   # cabecalho + 12 semanas


def test_planilhas_exigem_login(client):
    for url in ["/atividades/exportar/", "/estoque/movimentacoes/exportar/", "/paineis/evolucao.csv"]:
        assert client.get(url).status_code == 302, url
