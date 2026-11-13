"""Regras do estoque. O saldo e sempre a soma das movimentacoes (livro-razao imutavel).

Produto que controla numero de serie: cada unidade e um ItemSerie, e toda movimentacao precisa
dizer QUAIS unidades entram ou saem. Assim, saldo == unidades "em estoque" a qualquer momento.
"""
import re

from django.db import transaction
from django.utils import timezone

from .models import ItemSerie, MovimentacaoEstoque, Produto, TarefaReposicao


class EstoqueInsuficiente(Exception):
    pass


def ler_series(valor):
    """Aceita lista ou texto (um por linha, ou separados por virgula/ponto e virgula). Tira vazios e espacos."""
    if not valor:
        return []
    itens = valor if isinstance(valor, (list, tuple)) else re.split(r"[\n,;]+", str(valor))
    return [str(s).strip() for s in itens if str(s).strip()]


def _conferir_series(produto, series, quantidade):
    """Para produto com numero de serie: a quantidade e o numero de series informadas."""
    if not produto.controla_serie:
        if series:
            raise ValueError(f"{produto.nome} não controla número de série.")
        return quantidade
    if not series:
        raise ValueError(f"{produto.nome} controla número de série: informe (ou leia) os números de série.")
    repetidas = {s for s in series if series.count(s) > 1}
    if repetidas:
        raise ValueError(f"Número de série repetido na lista: {', '.join(sorted(repetidas))}.")
    if quantidade and quantidade != len(series):
        raise ValueError(f"Quantidade ({quantidade}) diferente da quantidade de números de série ({len(series)}).")
    return len(series)


def _criar_itens(produto, series, movimentacao):
    existentes = set(ItemSerie.objects.filter(produto=produto, numero_serie__in=series)
                     .values_list("numero_serie", flat=True))
    if existentes:
        raise ValueError(f"Número de série já cadastrado para {produto.nome}: {', '.join(sorted(existentes))}.")
    ItemSerie.objects.bulk_create([ItemSerie(produto=produto, numero_serie=s, entrada=movimentacao) for s in series])


def _itens_disponiveis(produto, series):
    """Trava e devolve as unidades informadas; erro dizendo qual serie nao esta no estoque."""
    itens = list(ItemSerie.objects.select_for_update().filter(produto=produto, numero_serie__in=series,
                                                              status=ItemSerie.Status.EM_ESTOQUE))
    faltando = set(series) - {i.numero_serie for i in itens}
    if faltando:
        raise EstoqueInsuficiente(f"Número de série fora do estoque de {produto.nome}: {', '.join(sorted(faltando))}.")
    return itens


def _retirar_itens(itens, movimentacao, novo_status):
    ItemSerie.objects.filter(pk__in=[i.pk for i in itens]).update(status=novo_status, saida=movimentacao)


@transaction.atomic
def registrar_entrada(produto, quantidade, usuario, observacao="", numeros_serie=None):
    produto = Produto.objects.select_for_update().get(pk=produto.pk)
    series = ler_series(numeros_serie)
    quantidade = _conferir_series(produto, series, quantidade)
    if not quantidade or quantidade <= 0:
        raise ValueError("Quantidade deve ser positiva.")
    if not produto.ativo:
        raise ValueError(f"{produto.nome} está inativo.")
    mov = MovimentacaoEstoque.objects.create(
        produto=produto, tipo=MovimentacaoEstoque.Tipo.ENTRADA,
        quantidade=quantidade, usuario=usuario, observacao=observacao)
    if series:
        _criar_itens(produto, series, mov)
    _verificar_reposicao(produto, mov)
    return mov


@transaction.atomic
def registrar_ajuste(produto, quantidade, usuario, observacao, numeros_serie=None):
    """Correcao de inventario (positiva ou negativa). Nunca edita o passado: registra a diferenca.

    Com numero de serie: ajuste positivo cadastra as unidades encontradas; negativo baixa as unidades informadas.
    """
    if not (observacao or "").strip():
        raise ValueError("Todo ajuste precisa de justificativa.")
    if not quantidade:
        raise ValueError("Informe uma quantidade diferente de zero (+ para somar, - para tirar).")
    produto = Produto.objects.select_for_update().get(pk=produto.pk)
    series = ler_series(numeros_serie)
    sinal = 1 if quantidade > 0 else -1
    quantidade = sinal * _conferir_series(produto, series, abs(quantidade))
    saindo = _itens_disponiveis(produto, series) if series and sinal < 0 else []
    if produto.saldo + quantidade < 0:
        raise EstoqueInsuficiente(f"O ajuste deixaria {produto.nome} com saldo negativo (saldo atual {produto.saldo}).")
    mov = MovimentacaoEstoque.objects.create(
        produto=produto, tipo=MovimentacaoEstoque.Tipo.AJUSTE,
        quantidade=quantidade, usuario=usuario, observacao=observacao.strip())
    if series and sinal > 0:
        _criar_itens(produto, series, mov)
    elif saindo:
        _retirar_itens(saindo, mov, ItemSerie.Status.BAIXADO)
    _verificar_reposicao(produto, mov)
    return mov


@transaction.atomic
def baixar_para_os(produto_id, quantidade, ordem, usuario, numeros_serie=None):
    """Saida de material usado numa OS. Trava o produto para evitar saldo negativo em acessos simultaneos."""
    produto = Produto.objects.select_for_update().get(pk=produto_id)
    series = ler_series(numeros_serie)
    quantidade = _conferir_series(produto, series, quantidade)
    if not quantidade or quantidade <= 0:
        raise ValueError("Quantidade deve ser positiva.")
    if produto.cliente_id and produto.cliente_id != ordem.cliente_id:
        raise ValueError(f"{produto.nome} pertence a outro cliente.")
    saindo = _itens_disponiveis(produto, series) if series else []
    if produto.saldo < quantidade:
        raise EstoqueInsuficiente(f"Estoque insuficiente de {produto.nome} (saldo {produto.saldo}).")
    observacao = f"Uso na OS {ordem.numero}" + (f" - SN {', '.join(series)}" if series else "")
    mov = MovimentacaoEstoque.objects.create(
        produto=produto, tipo=MovimentacaoEstoque.Tipo.SAIDA_OS, quantidade=-quantidade,
        ordem=ordem, usuario=usuario, observacao=observacao[:255])
    if saindo:
        _retirar_itens(saindo, mov, ItemSerie.Status.UTILIZADO)
    _verificar_reposicao(produto, mov)
    return mov


# ---------- Tarefas de reposicao (estoque -> gestao de tarefas) ----------

def quantidade_sugerida(produto, saldo):
    """Repor ate o dobro do estoque minimo (margem de seguranca simples); pelo menos 1 unidade."""
    return max(2 * produto.estoque_minimo - saldo, 1)


def _verificar_reposicao(produto, movimentacao):
    """Chamada depois de toda movimentacao, na mesma transacao.

    Saldo no minimo ou abaixo -> abre a tarefa (se ainda nao houver uma aberta).
    Saldo acima do minimo com tarefa aberta -> conclui a tarefa, ligada a movimentacao que repos.
    """
    saldo = produto.saldo
    aberta = TarefaReposicao.objects.select_for_update().filter(
        produto=produto, status=TarefaReposicao.Status.ABERTA).first()
    if saldo <= produto.estoque_minimo:
        if aberta is None and produto.ativo:
            TarefaReposicao.objects.create(
                produto=produto, saldo_na_abertura=saldo, minimo_na_abertura=produto.estoque_minimo,
                quantidade_sugerida=quantidade_sugerida(produto, saldo), origem=movimentacao)
    elif aberta is not None:
        aberta.status = TarefaReposicao.Status.CONCLUIDA
        aberta.encerrada_em = timezone.now()
        aberta.conclusao = movimentacao
        aberta.save(update_fields=["status", "encerrada_em", "conclusao"])


def _aberta(tarefa):
    tarefa = TarefaReposicao.objects.select_for_update().get(pk=tarefa.pk)
    if tarefa.status != TarefaReposicao.Status.ABERTA:
        raise ValueError("Esta tarefa de reposição já foi encerrada.")
    return tarefa


@transaction.atomic
def assumir_reposicao(tarefa, usuario):
    tarefa = _aberta(tarefa)
    tarefa.responsavel = usuario
    tarefa.save(update_fields=["responsavel"])
    return tarefa


@transaction.atomic
def cancelar_reposicao(tarefa, usuario, motivo):
    """Ex.: produto vai sair de linha. Se o saldo continuar baixo, a proxima movimentacao abre outra."""
    if not (motivo or "").strip():
        raise ValueError("Informe o motivo do cancelamento.")
    tarefa = _aberta(tarefa)
    tarefa.status = TarefaReposicao.Status.CANCELADA
    tarefa.encerrada_em = timezone.now()
    tarefa.motivo_cancelamento = f"{motivo.strip()} ({usuario})"[:255]
    tarefa.save(update_fields=["status", "encerrada_em", "motivo_cancelamento"])
    return tarefa
