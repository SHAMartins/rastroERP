"""Regras do estoque. O saldo e sempre a soma das movimentacoes (livro-razao imutavel).

Produto que controla numero de serie: cada unidade e um ItemSerie, e toda movimentacao precisa
dizer QUAIS unidades entram ou saem. Assim, saldo == unidades "em estoque" a qualquer momento.
"""
import re

from django.db import transaction

from .models import ItemSerie, MovimentacaoEstoque, Produto


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
            raise ValueError(f"{produto.nome} nao controla numero de serie.")
        return quantidade
    if not series:
        raise ValueError(f"{produto.nome} controla numero de serie: informe (ou leia) os numeros de serie.")
    repetidas = {s for s in series if series.count(s) > 1}
    if repetidas:
        raise ValueError(f"Numero de serie repetido na lista: {', '.join(sorted(repetidas))}.")
    if quantidade and quantidade != len(series):
        raise ValueError(f"Quantidade ({quantidade}) diferente da quantidade de numeros de serie ({len(series)}).")
    return len(series)


def _criar_itens(produto, series, movimentacao):
    existentes = set(ItemSerie.objects.filter(produto=produto, numero_serie__in=series)
                     .values_list("numero_serie", flat=True))
    if existentes:
        raise ValueError(f"Numero de serie ja cadastrado para {produto.nome}: {', '.join(sorted(existentes))}.")
    ItemSerie.objects.bulk_create([ItemSerie(produto=produto, numero_serie=s, entrada=movimentacao) for s in series])


def _itens_disponiveis(produto, series):
    """Trava e devolve as unidades informadas; erro dizendo qual serie nao esta no estoque."""
    itens = list(ItemSerie.objects.select_for_update().filter(produto=produto, numero_serie__in=series,
                                                              status=ItemSerie.Status.EM_ESTOQUE))
    faltando = set(series) - {i.numero_serie for i in itens}
    if faltando:
        raise EstoqueInsuficiente(f"Numero de serie fora do estoque de {produto.nome}: {', '.join(sorted(faltando))}.")
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
        raise ValueError(f"{produto.nome} esta inativo.")
    mov = MovimentacaoEstoque.objects.create(
        produto=produto, tipo=MovimentacaoEstoque.Tipo.ENTRADA,
        quantidade=quantidade, usuario=usuario, observacao=observacao)
    if series:
        _criar_itens(produto, series, mov)
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
    return mov
