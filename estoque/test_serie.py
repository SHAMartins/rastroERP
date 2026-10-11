"""Numero de serie por unidade: entrada, baixa por OS, ajuste, rastreio e scanner nas telas."""
import pytest

from chamados import services as chamados

from . import services
from .models import ItemSerie, Produto

pytestmark = pytest.mark.django_db
HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def ont(db):
    return Produto.objects.create(codigo="7891234567895", nome="ONT GPON", tipo="ONT", modelo="HG8245",
                                  controla_serie=True)


def em_estoque(produto):
    return produto.itens.filter(status=ItemSerie.Status.EM_ESTOQUE).count()


def test_entrada_cria_uma_unidade_por_serie(usuario, ont):
    mov = services.registrar_entrada(ont, None, usuario, "NF 10", "SN001\nSN002\n  SN003  \n")
    assert mov.quantidade == 3 and ont.saldo == 3 == em_estoque(ont)
    assert set(ont.itens.values_list("numero_serie", flat=True)) == {"SN001", "SN002", "SN003"}


def test_entrada_exige_series_validas(usuario, ont):
    with pytest.raises(ValueError, match="informe"):
        services.registrar_entrada(ont, 2, usuario)
    with pytest.raises(ValueError, match="repetido"):
        services.registrar_entrada(ont, None, usuario, numeros_serie="A1\nA1")
    with pytest.raises(ValueError, match="diferente"):
        services.registrar_entrada(ont, 3, usuario, numeros_serie="A1, A2")
    services.registrar_entrada(ont, None, usuario, numeros_serie="A1")
    with pytest.raises(ValueError, match="ja cadastrado"):
        services.registrar_entrada(ont, None, usuario, numeros_serie="A1")
    assert ont.saldo == 1


def test_produto_sem_serie_recusa_series(usuario):
    cabo = Produto.objects.create(codigo="CB", nome="Cabo drop", unidade="m")
    with pytest.raises(ValueError, match="nao controla"):
        services.registrar_entrada(cabo, 1, usuario, numeros_serie="X")


def test_baixa_na_os_registra_qual_unidade_foi_instalada(usuario, ordem, ont):
    services.registrar_entrada(ont, None, usuario, numeros_serie="SN1\nSN2")
    mov = services.baixar_para_os(ont.pk, None, ordem, usuario, "SN2")
    item = ont.itens.get(numero_serie="SN2")
    assert mov.quantidade == -1 and item.status == "UTILIZADO" and item.saida.ordem == ordem
    assert ont.saldo == 1 == em_estoque(ont)


def test_baixa_com_serie_fora_do_estoque_nao_grava_nada(usuario, ordem, ont):
    services.registrar_entrada(ont, None, usuario, numeros_serie="SN1")
    with pytest.raises(services.EstoqueInsuficiente, match="SN9"):
        services.baixar_para_os(ont.pk, None, ordem, usuario, "SN1, SN9")
    assert ont.saldo == 1 and ont.itens.get().status == "EM_ESTOQUE"     # transacao inteira desfeita


def test_ajuste_negativo_baixa_a_unidade_e_positivo_cadastra(usuario, ont):
    services.registrar_entrada(ont, None, usuario, numeros_serie="SN1\nSN2")
    services.registrar_ajuste(ont, -1, usuario, "Queimou na bancada", "SN1")
    services.registrar_ajuste(ont, 1, usuario, "Achado no inventario", "SN7")
    assert ont.itens.get(numero_serie="SN1").status == "BAIXADO"
    assert ont.saldo == 2 == em_estoque(ont)


def test_nao_troca_controle_de_serie_com_saldo(logado, usuario, ont):
    services.registrar_entrada(ont, None, usuario, numeros_serie="SN1")
    r = logado.post(f"/estoque/produtos/{ont.pk}/", {"codigo": ont.codigo, "nome": ont.nome, "unidade": "un",
                                                      "estoque_minimo": 0, "ativo": "on"})
    assert "saldo zerado" in str(r.context["form"].errors)


def test_entrada_pela_tela_com_series_lidas(logado, ont):
    r = logado.post(f"/estoque/produtos/{ont.pk}/entrada/",
                    {"entrada-numeros_serie": "SN10\nSN11", "entrada-observacao": "NF 99"}, **HTMX)
    html = r.content.decode()
    assert "Entrada de 2 un registrada" in html and "SN10" in html and "Unidades por numero de serie" in html


def test_busca_por_serie_mostra_onde_esta(logado, usuario, ordem, ont):
    services.registrar_entrada(ont, None, usuario, numeros_serie="SN-ABC")
    services.baixar_para_os(ont.pk, None, ordem, usuario, "SN-ABC")
    html = logado.get("/estoque/", {"q": "sn-abc"}).content.decode()
    assert "instalado na" in html and f"OS {ordem.numero}" in html and "Mercado Bom Preco" in html


def test_material_com_serie_pela_tela_da_atividade(logado, usuario, chamado, ordem, ont):
    services.registrar_entrada(ont, None, usuario, numeros_serie="SN5")
    pre = f"os{ordem.pk}"
    logado.post(f"/ordens/{ordem.pk}/material/", {f"{pre}-produto": ont.pk, f"{pre}-numeros_serie": "SN5"})
    assert ont.itens.get().status == "UTILIZADO"
    html = logado.get(f"/atividades/{chamado.pk}/").content.decode()
    assert "SN SN5" in html or "SN5" in html
    assert ordem.historico.filter(campo="material", valor_novo__contains="SN5").exists()


def test_telas_tem_botao_de_scanner(logado, ont, ordem, chamado):
    for url in ["/estoque/produtos/novo/", f"/estoque/produtos/{ont.pk}/", "/estoque/", f"/atividades/{chamado.pk}/"]:
        html = logado.get(url).content.decode()
        assert "data-scanner-alvo" in html and 'id="modal-scanner"' in html, url
