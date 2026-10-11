"""Estoque: regras de entrada/ajuste, telas (com HTMX) e fechamento da brecha do admin."""
import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from . import services
from .admin import MovimentacaoAdmin
from .models import MovimentacaoEstoque, Produto

pytestmark = pytest.mark.django_db
HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def produto(db):
    return Produto.objects.create(codigo="ONT-01", nome="ONT GPON", estoque_minimo=2)


def test_ajuste_exige_justificativa_e_quantidade(usuario, produto):
    with pytest.raises(ValueError, match="justificativa"):
        services.registrar_ajuste(produto, 1, usuario, "  ")
    with pytest.raises(ValueError, match="diferente de zero"):
        services.registrar_ajuste(produto, 0, usuario, "inventario")


def test_ajuste_nao_deixa_saldo_negativo(usuario, produto):
    services.registrar_entrada(produto, 3, usuario)
    with pytest.raises(services.EstoqueInsuficiente):
        services.registrar_ajuste(produto, -4, usuario, "perda")
    services.registrar_ajuste(produto, -3, usuario, "avaria no transporte")
    assert produto.saldo == 0


def test_produto_inativo_nao_recebe_entrada(usuario, produto):
    produto.ativo = False
    produto.save()
    with pytest.raises(ValueError, match="inativo"):
        services.registrar_entrada(produto, 1, usuario)


def test_admin_nao_cria_movimentacao(usuario):
    request = RequestFactory().get("/admin/")
    request.user = usuario
    assert MovimentacaoAdmin(MovimentacaoEstoque, AdminSite()).has_add_permission(request) is False


def test_cadastrar_produto_pela_tela(logado):
    r = logado.post("/estoque/produtos/novo/", {"codigo": "RT-1", "nome": "Roteador", "unidade": "un",
                                                 "estoque_minimo": 1, "ativo": "on"})
    p = Produto.objects.get(codigo="RT-1")
    assert r.url == f"/estoque/produtos/{p.pk}/" and p.saldo == 0


def test_entrada_via_htmx_atualiza_saldo_e_kardex(logado, produto):
    r = logado.post(f"/estoque/produtos/{produto.pk}/entrada/",
                    {"entrada-quantidade": 10, "entrada-observacao": "NF 123"}, **HTMX)
    html = r.content.decode()
    assert r.status_code == 200 and "<html" not in html          # so o bloco, sem a pagina inteira
    assert "Entrada de 10 un registrada" in html and "NF 123" in html
    assert produto.saldo == 10


def test_ajuste_invalido_mostra_erro_sem_gravar(logado, produto):
    r = logado.post(f"/estoque/produtos/{produto.pk}/ajuste/",
                    {"ajuste-quantidade": -1, "ajuste-observacao": "perda"}, **HTMX)
    assert "saldo negativo" in r.content.decode()
    assert produto.movimentacoes.count() == 0


def test_sem_htmx_redireciona_para_a_ficha(logado, produto):
    r = logado.post(f"/estoque/produtos/{produto.pk}/entrada/", {"entrada-quantidade": 2})
    assert r.status_code == 302 and r.url == f"/estoque/produtos/{produto.pk}/"


def test_lista_filtra_estoque_baixo(logado, usuario, produto):
    cheio = Produto.objects.create(codigo="CB-1", nome="Cabo", estoque_minimo=1)
    services.registrar_entrada(cheio, 50, usuario)
    r = logado.get("/estoque/?filtro=baixo")
    assert [p.pk for p in r.context["pagina"]] == [produto.pk]


def test_paginas_de_estoque_renderizam(logado, usuario, produto):
    services.registrar_entrada(produto, 5, usuario)
    for url in ["/estoque/", "/estoque/produtos/novo/", f"/estoque/produtos/{produto.pk}/", "/estoque/movimentacoes/"]:
        assert logado.get(url).status_code == 200, url
