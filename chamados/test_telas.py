"""Telas e API das atividades (chamado + OSs na mesma tela)."""
import pytest
from rest_framework.test import APIClient

from .models import Chamado

pytestmark = pytest.mark.django_db
FORM = {"tipo": "MANUTENCAO", "titulo": "Link down", "solicitante_nome": "Ana", "endereco": "Av. Brasil, 100",
        "cliente_final": "Farmacia Vida - Unidade Centro", "ativo": "CIRC-9", "impacto": "MEDIO", "urgencia": "ALTA",
        "d_sintoma": "Sem navegacao", "d_desde_quando": "2026-10-11T07:30", "d_afetados": "UNIDADE"}


def test_abrir_atividade_pela_tela(logado, cliente):
    resposta = logado.post("/atividades/novo/", {**FORM, "cliente": cliente.pk})
    c = Chamado.objects.get()
    assert resposta.status_code == 302 and resposta.url == f"/atividades/{c.pk}/"
    assert c.prioridade == "ALTA" and c.prazo_solucao is not None
    assert c.detalhes["afetados"] == "UNIDADE" and c.detalhes["desde_quando"].startswith("2026-10-11T07:30")
    html = logado.get(resposta.url).content.decode()
    assert "Quem esta afetado" in html and "Toda a unidade" in html


def test_campos_mudam_conforme_o_tipo(logado):
    manutencao = logado.get("/atividades/campos-tipo/", {"tipo": "MANUTENCAO"}).content.decode()
    instalacao = logado.get("/atividades/campos-tipo/", {"tipo": "INSTALACAO"}).content.decode()
    assert 'name="d_sintoma"' in manutencao and 'name="d_escopo"' not in manutencao
    assert 'name="d_escopo"' in instalacao and 'name="d_sintoma"' not in instalacao
    assert "descricao" not in manutencao


def test_formulario_exige_campos_do_tipo(logado, cliente):
    resposta = logado.post("/atividades/novo/", {**FORM, "cliente": cliente.pk, "d_afetados": ""})
    assert "d_afetados" in resposta.context["form"].errors
    assert not Chamado.objects.exists()


def test_formulario_exige_ativo_na_manutencao(logado, cliente):
    resposta = logado.post("/atividades/novo/", {**FORM, "cliente": cliente.pk, "ativo": ""})
    assert "ativo" in resposta.context["form"].errors
    assert not Chamado.objects.exists()


def test_previa_mostra_prioridade_e_prazos(logado, cliente):
    html = logado.get("/atividades/previa-sla/", {"cliente": cliente.pk, "tipo": "MANUTENCAO",
                                                   "impacto": "ALTO", "urgencia": "ALTA"}).content.decode()
    assert "Urgente" in html and "4h" in html and "SLA padrao" in html


def test_gerar_os_leva_para_a_os_dentro_da_atividade(logado, chamado):
    resposta = logado.post(f"/atividades/{chamado.pk}/gerar-os/",
                           {"nova_os-titulo": "Ir ao local", "nova_os-prioridade": "ALTA"})
    ordem = chamado.ordens.get()
    destino = logado.get(resposta.url)            # /ordens/<id>/ redireciona para a atividade
    assert destino.url == f"/atividades/{chamado.pk}/#os-{ordem.pk}"


def test_os_aparece_e_e_operada_na_tela_da_atividade(logado, chamado, ordem):
    pre = f"os{ordem.pk}"
    resposta = logado.post(f"/ordens/{ordem.pk}/status/", {f"{pre}-status": "EM_ANDAMENTO"})
    assert resposta.url == f"/atividades/{chamado.pk}/#os-{ordem.pk}"
    html = logado.get(f"/atividades/{chamado.pk}/").content.decode()
    assert f'id="os-{ordem.pk}"' in html and "Verificar ONT" in html
    assert f'name="{pre}-status"' in html and f'name="{pre}-produto"' in html   # status e material na mesma tela
    assert "Em andamento" in html                                               # historico da OS na linha do tempo


def test_lista_mostra_a_execucao_e_filtra_minhas_os(logado, usuario, chamado, ordem):
    ordem.responsavel = usuario
    ordem.save()
    html = logado.get("/atividades/?minhas=1").content.decode()
    assert chamado.numero in html and f"OS {ordem.numero}" in html
    assert logado.get("/ordens/").url == "/atividades/"


def test_resolver_pela_tela(logado, chamado):
    logado.post(f"/atividades/{chamado.pk}/status/", {"status": "RESOLVIDO", "nota_resolucao": "Reset remoto",
                                                      "categoria_encerramento": "REMOTO"})
    chamado.refresh_from_db()
    assert chamado.status == "RESOLVIDO"


def test_paginas_renderizam(logado, chamado, ordem):
    for url in ["/", "/paineis/triagem/", "/paineis/manutencao/", "/paineis/instalacao/",
                "/atividades/", "/atividades/novo/", f"/atividades/{chamado.pk}/"]:
        assert logado.get(url).status_code == 200, url


def test_api_abre_chamado_e_gera_os(usuario, cliente):
    api = APIClient()
    api.force_authenticate(usuario)
    dados = {k: v for k, v in FORM.items() if not k.startswith("d_")}
    dados["detalhes"] = {"sintoma": "Sem navegacao", "desde_quando": "2026-10-11T07:30", "afetados": "SETOR"}
    r = api.post("/api/chamados/", {**dados, "cliente": cliente.pk}, format="json")
    assert r.status_code == 201 and r.data["prioridade"] == "ALTA" and r.data["status"] == "NOVO"
    r2 = api.post(f"/api/chamados/{r.data['id']}/gerar-os/", {}, format="json")
    assert r2.status_code == 201 and r2.data["chamado"] == r.data["id"]
    assert api.delete(f"/api/chamados/{r.data['id']}/").status_code == 405
    sem_detalhes = api.post("/api/chamados/", {**dados, "cliente": cliente.pk, "detalhes": {}}, format="json")
    assert sem_detalhes.status_code == 400
