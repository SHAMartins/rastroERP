"""OS dentro da atividade: endereco vindo do chamado, status e material."""
import pytest

from chamados import services as chamados
from clientes.models import Cliente, Servico
from estoque import services as estoque
from estoque.models import Produto

from . import services

pytestmark = pytest.mark.django_db


def test_acoes_exigem_login(client, ordem):
    assert client.post(f"/ordens/{ordem.pk}/status/").status_code == 302


def test_os_herda_cliente_e_endereco_do_chamado(chamado, ordem):
    assert ordem.cliente_id == chamado.cliente_id
    assert ordem.endereco == "Rua B, 2"
    assert ordem.numero.count("-") == 1          # formato ANO-SEQUENCIA


def test_servico_exclusivo_de_outro_cliente_e_recusado(usuario, chamado):
    outro = Cliente.objects.create(nome="Outro", documento="22.222.222/0001-22")
    servico_outro = Servico.objects.create(cliente=outro, nome="Manutencao especial")
    with pytest.raises(ValueError):
        chamados.gerar_os(chamado, usuario, servico=servico_outro)


def test_comentario_da_os_aparece_na_atividade(logado, usuario, chamado, ordem):
    services.comentar(ordem, usuario, "Tecnico a caminho")
    html = logado.get(f"/atividades/{chamado.pk}/").content.decode()
    assert "Tecnico a caminho" in html and f"OS {ordem.numero}" in html


def test_usar_material_baixa_estoque(logado, usuario, ordem):
    produto = Produto.objects.create(codigo="P1", nome="ONT GPON")
    estoque.registrar_entrada(produto, 5, usuario)
    pre = f"os{ordem.pk}"
    logado.post(f"/ordens/{ordem.pk}/material/", {f"{pre}-produto": produto.pk, f"{pre}-quantidade": 2})
    assert produto.saldo == 3
    assert ordem.movimentacoes.count() == 1


def test_material_sem_saldo_nao_grava_nada(logado, ordem):
    produto = Produto.objects.create(codigo="P2", nome="Roteador")
    pre = f"os{ordem.pk}"
    resposta = logado.post(f"/ordens/{ordem.pk}/material/", {f"{pre}-produto": produto.pk, f"{pre}-quantidade": 1},
                           follow=True)
    assert "Estoque insuficiente" in resposta.content.decode()
    assert produto.movimentacoes.count() == 0
    assert not ordem.historico.filter(campo="material").exists()
