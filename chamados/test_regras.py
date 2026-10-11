"""Regras do chamado: numeracao, matriz de prioridade, SLA (calculo, pausa, situacao) e encerramento."""
from datetime import timedelta

import pytest
from django.db.models import ProtectedError
from django.utils import timezone

from . import services
from .models import Chamado, PoliticaSLA

pytestmark = pytest.mark.django_db
DETALHES_INCIDENTE = {"sintoma": "Sem sinal", "desde_quando": "2026-10-11T08:00", "afetados": "USUARIO"}
DADOS = dict(tipo="MANUTENCAO", titulo="Sem sinal", solicitante_nome="Ana", endereco="Rua A, 1", ativo="CIRC-1",
             detalhes=DETALHES_INCIDENTE)


def test_numero_automatico(chamado):
    assert chamado.numero == f"CH-{timezone.now().year}-00001"


@pytest.mark.parametrize("impacto,urgencia,esperada", [
    ("ALTO", "ALTA", "URGENTE"), ("ALTO", "BAIXA", "MEDIA"), ("MEDIO", "MEDIA", "MEDIA"), ("BAIXO", "BAIXA", "BAIXA")])
def test_matriz_de_prioridade(usuario, cliente, impacto, urgencia, esperada):
    c = services.abrir_chamado(usuario, cliente=cliente, impacto=impacto, urgencia=urgencia, **DADOS)
    assert c.prioridade == esperada


def test_sla_padrao_aplicado_na_abertura(chamado):
    # Manutencao urgente no SLA padrao: resposta 0,5h e solucao 4h
    assert chamado.prazo_resposta - chamado.aberto_em == timedelta(minutes=30)
    assert chamado.prazo_solucao - chamado.aberto_em == timedelta(hours=4)
    assert chamado.situacao_sla == "NO_PRAZO"


def test_sla_do_contrato_tem_preferencia(usuario, cliente):
    PoliticaSLA.objects.create(cliente=cliente, tipo="MANUTENCAO", prioridade="URGENTE",
                               horas_resposta=0.25, horas_solucao=2)
    c = services.abrir_chamado(usuario, cliente=cliente, impacto="ALTO", urgencia="ALTA", **DADOS)
    assert c.prazo_solucao - c.aberto_em == timedelta(hours=2)


def test_manutencao_exige_ativo(usuario, cliente):
    with pytest.raises(ValueError):
        services.abrir_chamado(usuario, cliente=cliente, **{**DADOS, "ativo": ""})


def test_instalacao_nao_exige_ativo(usuario, cliente):
    detalhes = {"servico_contratado": "LINK_DEDICADO", "escopo": "Ativar link 500M", "prerequisitos": "OK"}
    c = services.abrir_chamado(usuario, cliente=cliente, **{**DADOS, "tipo": "INSTALACAO", "ativo": "",
                                                           "detalhes": detalhes})
    assert c.pk


def test_cada_tipo_exige_os_seus_campos(usuario, cliente):
    # Os campos obrigatorios da manutencao nao servem para instalacao
    with pytest.raises(ValueError, match="Servico"):
        services.abrir_chamado(usuario, cliente=cliente, **{**DADOS, "tipo": "INSTALACAO"})
    with pytest.raises(ValueError, match="Quem esta afetado"):
        services.abrir_chamado(usuario, cliente=cliente, **{**DADOS, "detalhes": {"sintoma": "x"}})


def test_manutencao_programada_nao_exige_data_do_problema(usuario, cliente):
    c = services.abrir_chamado(usuario, cliente=cliente,
                               **{**DADOS, "detalhes": {"sintoma": "Troca de baterias", "afetados": "NINGUEM"}})
    assert "desde_quando" not in c.detalhes


def test_detalhes_descartam_campos_de_outro_tipo_e_validam_opcoes(usuario, cliente):
    c = services.abrir_chamado(usuario, cliente=cliente,
                               **{**DADOS, "detalhes": {**DETALHES_INCIDENTE, "escopo": "nao e da manutencao"}})
    assert "escopo" not in c.detalhes
    with pytest.raises(ValueError, match="Opcao invalida"):
        services.abrir_chamado(usuario, cliente=cliente,
                               **{**DADOS, "detalhes": {**DETALHES_INCIDENTE, "afetados": "TODO_MUNDO"}})
    with pytest.raises(ValueError, match="Data invalida"):
        services.abrir_chamado(usuario, cliente=cliente,
                               **{**DADOS, "detalhes": {**DETALHES_INCIDENTE, "desde_quando": "ontem"}})


def test_alterar_detalhe_gera_historico(usuario, chamado):
    services.atualizar_chamado(chamado, usuario, detalhes={**chamado.detalhes, "afetados": "VARIAS"})
    h = chamado.historico.get(campo="detalhe.afetados")
    assert (h.valor_anterior, h.valor_novo) == ("Toda a unidade", "Varias unidades")


def test_reclassificar_recalcula_prioridade_e_prazo(usuario, chamado):
    c = services.atualizar_chamado(chamado, usuario, impacto="BAIXO", urgencia="BAIXA")
    assert c.prioridade == "BAIXA"
    assert c.prazo_solucao - c.aberto_em == timedelta(hours=72)
    assert c.historico.filter(campo="prioridade", valor_anterior="Urgente", valor_novo="Baixa").exists()


def test_gerar_os_tira_da_triagem_e_marca_primeira_resposta(usuario, chamado):
    ordem = services.gerar_os(chamado, usuario)
    chamado.refresh_from_db()
    assert ordem.chamado == chamado and ordem.titulo == chamado.titulo and ordem.prioridade == "URGENTE"
    assert chamado.status == "EM_ATENDIMENTO"
    assert chamado.primeira_resposta_em is not None
    assert chamado.historico.filter(campo="os").exists()


def test_comentario_conta_como_primeira_resposta(usuario, chamado):
    services.comentar(chamado, usuario, "Verificando alarmes na OLT")
    chamado.refresh_from_db()
    assert chamado.primeira_resposta_em is not None
    assert chamado.resposta_no_prazo is True


def test_pendente_cliente_pausa_o_sla(usuario, chamado):
    services.atualizar_chamado(chamado, usuario, status="PENDENTE_CLIENTE")
    # simula 2h aguardando o cliente
    Chamado.objects.filter(pk=chamado.pk).update(pausado_desde=timezone.now() - timedelta(hours=2))
    chamado.refresh_from_db()
    assert chamado.situacao_sla == "PAUSADO"
    c = services.atualizar_chamado(chamado, usuario, status="EM_ATENDIMENTO")
    assert c.tempo_pausado >= timedelta(hours=2)
    assert c.prazo_solucao_efetivo == c.prazo_solucao + c.tempo_pausado


def test_situacao_em_risco_e_estourado(chamado):
    agora = timezone.now()
    Chamado.objects.filter(pk=chamado.pk).update(aberto_em=agora - timedelta(hours=3.5),
                                                 prazo_solucao=agora + timedelta(minutes=30))
    chamado.refresh_from_db()
    assert chamado.situacao_sla == "EM_RISCO"          # 87% do prazo consumido
    Chamado.objects.filter(pk=chamado.pk).update(prazo_solucao=agora - timedelta(minutes=1))
    chamado.refresh_from_db()
    assert chamado.situacao_sla == "ESTOURADO"


def test_resolver_exige_nota_e_categoria(usuario, chamado):
    with pytest.raises(ValueError):
        services.atualizar_chamado(chamado, usuario, status="RESOLVIDO")


def test_nao_resolve_com_os_aberta(usuario, chamado, ordem):
    with pytest.raises(ValueError, match="OSs"):
        services.atualizar_chamado(chamado, usuario, status="RESOLVIDO", nota_resolucao="Trocada ONT",
                                   categoria_encerramento="CAMPO")


def test_resolver_dentro_do_prazo_cumpre_sla(usuario, chamado):
    c = services.atualizar_chamado(chamado, usuario, status="RESOLVIDO", nota_resolucao="Reset remoto da ONT",
                                   causa="Travamento da ONT", categoria_encerramento="REMOTO")
    assert c.resolvido_em is not None
    assert c.situacao_sla == "CUMPRIDO"
    with pytest.raises(ValueError):                    # encerrado nao gera OS
        services.gerar_os(c, usuario)


def test_reabrir_limpa_resolucao(usuario, chamado):
    c = services.atualizar_chamado(chamado, usuario, status="RESOLVIDO", nota_resolucao="ok",
                                   categoria_encerramento="REMOTO")
    c = services.atualizar_chamado(c, usuario, status="EM_ATENDIMENTO")
    assert c.resolvido_em is None


def test_chamado_nao_pode_ser_apagado(chamado):
    with pytest.raises(ProtectedError):
        chamado.delete()
