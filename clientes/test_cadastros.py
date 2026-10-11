"""Cadastros: clientes (documento, contrato de SLA), servicos e SLA padrao."""
from datetime import timedelta

import pytest

from chamados import services as chamados
from chamados.models import PoliticaSLA

from .models import Cliente, Servico

pytestmark = pytest.mark.django_db


def test_cadastrar_cliente_normaliza_documento(logado):
    r = logado.post("/cadastros/clientes/novo/", {"nome": "Fibra Norte", "documento": "12345678000199", "ativo": "on"})
    c = Cliente.objects.get(nome="Fibra Norte")
    assert c.documento == "12.345.678/0001-99" and r.url == f"/cadastros/clientes/{c.pk}/"


def test_documento_invalido_ou_repetido(logado, cliente):
    r = logado.post("/cadastros/clientes/novo/", {"nome": "X", "documento": "123"})
    assert "documento" in r.context["form"].errors
    r = logado.post("/cadastros/clientes/novo/", {"nome": "Y", "documento": "11111111000111"})   # = fixture
    assert "Ja existe" in str(r.context["form"].errors["documento"])


def test_contrato_de_sla_substitui_o_padrao_na_abertura(logado, usuario, cliente):
    logado.post(f"/cadastros/clientes/{cliente.pk}/sla/", {"MANUTENCAO-URGENTE-resposta": "0,25",
                                                          "MANUTENCAO-URGENTE-solucao": "2"})
    assert PoliticaSLA.objects.filter(cliente=cliente).count() == 1
    c = chamados.abrir_chamado(usuario, tipo="MANUTENCAO", cliente=cliente, titulo="x", solicitante_nome="a",
                               endereco="r", ativo="A1", impacto="ALTO", urgencia="ALTA",
                               detalhes={"sintoma": "x", "afetados": "USUARIO"})
    assert c.prazo_solucao - c.aberto_em == timedelta(hours=2)


def test_celula_vazia_volta_a_usar_o_padrao(logado, cliente):
    PoliticaSLA.objects.create(cliente=cliente, tipo="MANUTENCAO", prioridade="ALTA", horas_resposta=1, horas_solucao=5)
    logado.post(f"/cadastros/clientes/{cliente.pk}/sla/", {})
    assert not PoliticaSLA.objects.filter(cliente=cliente).exists()


def test_sla_invalido_nao_grava_nada(logado, cliente):
    r = logado.post(f"/cadastros/clientes/{cliente.pk}/sla/", {
        "MANUTENCAO-BAIXA-resposta": "4", "MANUTENCAO-BAIXA-solucao": "8",
        "INSTALACAO-ALTA-resposta": "10", "INSTALACAO-ALTA-solucao": "2"})    # solucao < resposta
    assert r.status_code == 200 and "menor que a primeira resposta" in r.content.decode()
    assert not PoliticaSLA.objects.filter(cliente=cliente).exists()           # nem a celula valida


def test_editar_sla_padrao(logado):
    dados = {f"{p.tipo}-{p.prioridade}-{campo}": getattr(p, "horas_" + campo)
             for p in PoliticaSLA.objects.filter(cliente=None) for campo in ("resposta", "solucao")}
    dados["INSTALACAO-BAIXA-solucao"] = "400"
    logado.post("/cadastros/sla/", dados)
    assert PoliticaSLA.objects.get(cliente=None, tipo="INSTALACAO", prioridade="BAIXA").horas_solucao == 400


def test_cadastrar_servico(logado, cliente):
    logado.post("/cadastros/servicos/", {"nome": "Vistoria tecnica", "cliente": cliente.pk})
    assert Servico.objects.get(nome="Vistoria tecnica").cliente == cliente


def test_paginas_de_cadastro_renderizam(logado, cliente):
    for url in ["/cadastros/clientes/", "/cadastros/clientes/novo/", f"/cadastros/clientes/{cliente.pk}/",
                f"/cadastros/clientes/{cliente.pk}/sla/", "/cadastros/sla/", "/cadastros/servicos/"]:
        assert logado.get(url).status_code == 200, url
