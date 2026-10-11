"""Paineis: geral, triagem, manutencao e instalacao."""
from datetime import timedelta

import pytest
from django.utils import timezone

from chamados import services
from chamados.models import Chamado

pytestmark = pytest.mark.django_db
INSTALACAO = dict(tipo="INSTALACAO", titulo="Ativar link 500M", solicitante_nome="Rui", endereco="Rua C, 3",
                  detalhes={"servico_contratado": "LINK_DEDICADO", "escopo": "Ativacao", "prerequisitos": "PENDENTE",
                            "pendencias": "Falta autorizacao do condominio"})


def test_geral_mostra_status_de_atividades_e_os(logado, chamado, ordem):
    r = logado.get("/")
    assert r.context["ind"]["abertos"] == 1
    status = {i["codigo"]: i["total"] for i in r.context["status_chamados"]["itens"]}
    assert status["EM_ATENDIMENTO"] == 1                  # gerar a OS tirou a atividade da triagem
    os_status = {i["codigo"]: i["total"] for i in r.context["status_os"]["itens"]}
    assert os_status["ABERTA"] == 1


def test_sla_estourado_entra_nos_indicadores(logado, chamado):
    Chamado.objects.filter(pk=chamado.pk).update(prazo_solucao=timezone.now() - timedelta(minutes=5))
    assert logado.get("/").context["ind"]["estourados"] == 1


def test_triagem_lista_novos_e_resposta_vencida(logado, chamado):
    Chamado.objects.filter(pk=chamado.pk).update(prazo_resposta=timezone.now() - timedelta(minutes=1))
    r = logado.get("/paineis/triagem/")
    assert [c.pk for c in r.context["novos"]] == [chamado.pk]
    assert r.context["vencidos"] == 1


def test_manutencao_conta_ativos_e_afetados(logado, chamado):
    r = logado.get("/paineis/manutencao/")
    assert r.context["top_ativos"][0] == {"ativo": "CIRC-0001", "total": 1}
    afetados = {i["nome"]: i["total"] for i in r.context["afetados"]}
    assert afetados["Toda a unidade"] == 1


def test_instalacao_mostra_pendencias_e_sem_os(logado, usuario, cliente, chamado):
    inst = services.abrir_chamado(usuario, cliente=cliente, **INSTALACAO)
    r = logado.get("/paineis/instalacao/")
    assert [c.pk for c in r.context["com_pendencia"]] == [inst.pk]
    assert [c.pk for c in r.context["sem_os"]] == [inst.pk]
    assert r.context["ind"]["abertos"] == 1               # a manutencao nao entra no painel de instalacao
    assert "Falta autorizacao do condominio" in r.content.decode()
