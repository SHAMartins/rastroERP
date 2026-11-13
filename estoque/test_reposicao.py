"""Tarefas de reposicao: criadas quando o saldo chega ao minimo, concluidas pela entrada que repoe."""
import pytest
from django.db import IntegrityError

from . import services
from .models import Produto, TarefaReposicao as T

pytestmark = pytest.mark.django_db


@pytest.fixture
def cabo(db):
    return Produto.objects.create(codigo="CB-1", nome="Cabo drop", unidade="m", estoque_minimo=10)


def abertas(produto):
    return produto.reposicoes.filter(status=T.Status.ABERTA)


def test_baixa_na_os_que_atinge_o_minimo_abre_tarefa(usuario, ordem, cabo):
    services.registrar_entrada(cabo, 15, usuario)
    services.baixar_para_os(cabo.pk, 4, ordem, usuario)          # saldo 11: ainda acima do minimo
    assert not abertas(cabo).exists()
    mov = services.baixar_para_os(cabo.pk, 1, ordem, usuario)    # saldo 10 = minimo
    tarefa = abertas(cabo).get()
    assert tarefa.origem == mov and tarefa.origem.ordem == ordem
    assert (tarefa.saldo_na_abertura, tarefa.quantidade_sugerida) == (10, 10)   # repor ate o dobro do minimo


def test_nao_duplica_tarefa_enquanto_estiver_aberta(usuario, ordem, cabo):
    services.registrar_entrada(cabo, 12, usuario)
    services.baixar_para_os(cabo.pk, 3, ordem, usuario)
    services.baixar_para_os(cabo.pk, 3, ordem, usuario)
    assert abertas(cabo).count() == 1


def test_entrada_que_repoe_conclui_a_tarefa(usuario, cabo):
    services.registrar_entrada(cabo, 12, usuario)
    services.registrar_ajuste(cabo, -5, usuario, "perda")        # saldo 7: abre
    entrada = services.registrar_entrada(cabo, 2, usuario)        # saldo 9: ainda no minimo, continua aberta
    assert abertas(cabo).exists()
    entrada = services.registrar_entrada(cabo, 13, usuario, "NF 55")   # saldo 22: conclui
    tarefa = cabo.reposicoes.get()
    assert tarefa.status == T.Status.CONCLUIDA and tarefa.conclusao == entrada and tarefa.encerrada_em


def test_ajuste_negativo_tambem_abre_tarefa(usuario, cabo):
    services.registrar_entrada(cabo, 11, usuario)
    services.registrar_ajuste(cabo, -2, usuario, "inventario")
    assert abertas(cabo).get().saldo_na_abertura == 9


def test_produto_sem_minimo_so_abre_ao_zerar(usuario, ordem):
    ont = Produto.objects.create(codigo="RT", nome="Roteador", estoque_minimo=0)
    services.registrar_entrada(ont, 2, usuario)
    services.baixar_para_os(ont.pk, 1, ordem, usuario)
    assert not abertas(ont).exists()
    services.baixar_para_os(ont.pk, 1, ordem, usuario)
    assert abertas(ont).get().quantidade_sugerida == 1


def test_banco_impede_duas_tarefas_abertas_do_mesmo_produto(usuario, cabo):
    services.registrar_entrada(cabo, 10, usuario)                  # saldo 10 = minimo: abre
    with pytest.raises(IntegrityError):
        T.objects.create(produto=cabo, saldo_na_abertura=10, minimo_na_abertura=10, quantidade_sugerida=10,
                         origem=cabo.movimentacoes.get())


def test_assumir_e_cancelar_pela_tela_exigem_perfil_estoque(client, com_perfil, usuario, cabo):
    services.registrar_entrada(cabo, 10, usuario)
    tarefa = abertas(cabo).get()
    client.force_login(com_perfil("Técnico"))
    assert client.post(f"/estoque/reposicao/{tarefa.pk}/assumir/").status_code == 403
    estoquista = com_perfil("Estoque")
    client.force_login(estoquista)
    client.post(f"/estoque/reposicao/{tarefa.pk}/assumir/")
    tarefa.refresh_from_db()
    assert tarefa.responsavel == estoquista
    client.post(f"/estoque/reposicao/{tarefa.pk}/cancelar/", {"motivo": ""})
    tarefa.refresh_from_db()
    assert tarefa.status == T.Status.ABERTA                          # sem motivo nao cancela
    client.post(f"/estoque/reposicao/{tarefa.pk}/cancelar/", {"motivo": "Produto saiu de linha"})
    tarefa.refresh_from_db()
    assert tarefa.status == T.Status.CANCELADA and "saiu de linha" in tarefa.motivo_cancelamento


def test_tarefa_aparece_na_lista_no_painel_e_na_ficha(logado, usuario, cabo):
    services.registrar_entrada(cabo, 10, usuario)
    assert "Cabo drop" in logado.get("/estoque/reposicao/").content.decode()
    assert "1 tarefa de reposição aberta" in logado.get("/").content.decode()
    assert "Tarefa de reposição aberta" in logado.get(f"/estoque/produtos/{cabo.pk}/").content.decode()
    assert len(logado.get("/api/reposicoes/?status=ABERTA").json()) == 1
