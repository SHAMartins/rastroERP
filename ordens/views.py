"""Acoes da OS. Nao ha tela separada de OS: ela e exibida e operada dentro da atividade (chamado).

Toda regra passa por services.py.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from estoque.models import Produto
from estoque.services import EstoqueInsuficiente

from seguranca.permissoes import exigir_operar_os

from . import services
from .forms import MaterialForm, StatusForm
from .models import OrdemServico

ERROS = (ValueError, EstoqueInsuficiente, Produto.DoesNotExist)
ROTULOS_HISTORICO = {"criacao": "Abertura", "material": "Material utilizado"}


def prefixo(ordem):
    """Prefixo dos formularios de cada OS (varias OSs na mesma pagina da atividade)."""
    return f"os{ordem.pk}"


def _na_atividade(ordem):
    return redirect(reverse("chamados:detalhe", args=[ordem.chamado_id]) + f"#os-{ordem.pk}")


def eventos_da_os(ordem):
    """Comentarios e historico da OS, no formato da linha do tempo da atividade."""
    itens = [{"data": c.criado_em, "usuario": c.autor, "tipo": "comentario", "texto": c.texto, "os": ordem.numero}
             for c in ordem.comentarios.select_related("autor")]
    for h in ordem.historico.select_related("usuario"):
        rotulo = ROTULOS_HISTORICO.get(h.campo) or OrdemServico._meta.get_field(h.campo).verbose_name.capitalize()
        itens.append({"data": h.alterado_em, "usuario": h.usuario, "tipo": f"os_{h.campo}", "campo": rotulo,
                      "antes": h.valor_anterior, "depois": h.valor_novo, "os": ordem.numero})
    return itens


@login_required
def lista(request):
    return redirect("chamados:lista")


@login_required
def detalhe(request, pk):
    return _na_atividade(get_object_or_404(OrdemServico, pk=pk))


@login_required
@require_POST
def alterar_status(request, pk):
    ordem = get_object_or_404(OrdemServico, pk=pk)
    exigir_operar_os(request.user, ordem)
    form = StatusForm(request.POST, prefix=prefixo(ordem))
    try:
        if not form.is_valid():
            raise ValueError("Status invalido.")
        services.atualizar_os(ordem, request.user, status=form.cleaned_data["status"])
        messages.success(request, f"Status da OS {ordem.numero} atualizado.")
    except ValueError as e:
        messages.error(request, str(e))
    return _na_atividade(ordem)


@login_required
@require_POST
def usar_material(request, pk):
    ordem = get_object_or_404(OrdemServico, pk=pk)
    exigir_operar_os(request.user, ordem)
    form = MaterialForm(request.POST, ordem=ordem, prefix=prefixo(ordem))
    try:
        if not form.is_valid():
            raise ValueError("Escolha o produto e uma quantidade maior que zero.")
        mov = services.registrar_material(ordem, request.user, form.cleaned_data["produto"].pk,
                                          form.cleaned_data["quantidade"], form.cleaned_data["numeros_serie"])
        messages.success(request, f"Baixa de {-mov.quantidade} {mov.produto.unidade} de {mov.produto.nome}.")
    except ERROS as e:
        messages.error(request, str(e))
    return _na_atividade(ordem)
