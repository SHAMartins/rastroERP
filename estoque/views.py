"""Estoque: produtos, ficha com historico (kardex), entrada, ajuste e livro de movimentacoes."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from clientes.models import Cliente

from seguranca.permissoes import exigir

from . import services
from .forms import AjusteForm, EntradaForm, ProdutoForm
from .models import ItemSerie, MovimentacaoEstoque, Produto


def _com_saldo(produtos):
    """Saldo calculado no banco (uma consulta para a lista toda), igual a Produto.saldo."""
    return produtos.annotate(saldo_atual=Coalesce(Sum("movimentacoes__quantidade"), Value(0))).order_by("nome")


@login_required
def produtos(request):
    busca = request.GET.get("q", "").strip()
    filtro = request.GET.get("filtro", "")
    cliente = request.GET.get("cliente", "")
    tipo = request.GET.get("tipo", "")
    lista = _com_saldo(Produto.objects.select_related("cliente")).filter(ativo=filtro != "inativos")
    if filtro == "baixo":
        lista = lista.filter(saldo_atual__lte=F("estoque_minimo"))
    if cliente == "empresa":
        lista = lista.filter(cliente__isnull=True)
    elif cliente.isdigit():
        lista = lista.filter(cliente_id=cliente)
    if tipo:
        lista = lista.filter(tipo=tipo)
    if busca:
        lista = lista.filter(Q(nome__icontains=busca) | Q(codigo__icontains=busca) | Q(modelo__icontains=busca)
                             | Q(id__in=ItemSerie.objects.filter(numero_serie__icontains=busca).values("produto")))
    pagina = Paginator(lista, 30).get_page(request.GET.get("pagina"))
    # Leitura de um numero de serie exato responde "onde esta este equipamento?"
    series = (ItemSerie.objects.filter(numero_serie__iexact=busca)
              .select_related("produto", "saida__ordem__chamado") if busca else [])
    return render(request, "estoque/produtos.html", {
        "pagina": pagina, "busca": busca, "filtro": filtro, "cliente": cliente, "tipo": tipo, "series": series,
        "tipos": _tipos(), "clientes": Cliente.objects.filter(produtos__isnull=False).distinct()})


def _tipos():
    return Produto.objects.exclude(tipo="").order_by("tipo").values_list("tipo", flat=True).distinct()


def _kardex(produto):
    """Movimentacoes com o saldo depois de cada uma (do mais recente para o mais antigo)."""
    movs = list(produto.movimentacoes.select_related("usuario", "ordem")
                .prefetch_related("itens_entrada", "itens_saida").order_by("criado_em", "pk"))
    saldo = 0
    for m in movs:
        saldo += m.quantidade
        m.saldo_apos = saldo
    return list(reversed(movs))


def _eh_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _contexto_ficha(produto, form_entrada=None, form_ajuste=None, aviso=""):
    itens = produto.itens.select_related("saida__ordem__chamado") if produto.controla_serie else None
    return {"produto": produto, "kardex": _kardex(produto), "aviso": aviso, "itens": itens,
            "form_entrada": form_entrada or EntradaForm(prefix="entrada"),
            "form_ajuste": form_ajuste or AjusteForm(prefix="ajuste")}


@login_required
def produto_form(request, pk=None):
    produto = get_object_or_404(Produto, pk=pk) if pk else None
    permissao = "estoque.change_produto" if produto else "estoque.add_produto"
    pode_editar = request.user.has_perm(permissao)
    if request.method == "POST" or not produto:
        exigir(request.user, permissao)
    form = ProdutoForm(request.POST or None, instance=produto)
    if not pode_editar:
        for campo in form.fields.values():
            campo.disabled = True
    if request.method == "POST" and form.is_valid():
        salvo = form.save()
        messages.success(request, f"Produto {salvo.nome} {'atualizado' if produto else 'cadastrado'}.")
        return redirect("estoque:produto", pk=salvo.pk)
    contexto = _contexto_ficha(produto) if produto else {"produto": None}
    return render(request, "estoque/produto.html", {**contexto, "form": form, "tipos": _tipos(),
                                                    "pode_editar": pode_editar})


def _lancar(request, pk, form_cls, prefixo, acao, sucesso):
    """Entrada/ajuste. Com HTMX devolve so o bloco de saldo + kardex; sem JS, redireciona (PRG)."""
    exigir(request.user, "estoque.movimentar_estoque")
    produto = get_object_or_404(Produto, pk=pk)
    form = form_cls(request.POST, prefix=prefixo)
    aviso = ""
    if form.is_valid():
        try:
            mov = acao(produto, form.cleaned_data["quantidade"], request.user, form.cleaned_data["observacao"],
                       form.cleaned_data["numeros_serie"])
        except (ValueError, services.EstoqueInsuficiente) as e:
            form.add_error(None, str(e))
        else:
            aviso, form = sucesso(mov), None
    if not _eh_htmx(request):
        if aviso:
            messages.success(request, aviso)
        else:
            messages.error(request, " ".join(e for erros in form.errors.values() for e in erros))
        return redirect("estoque:produto", pk=pk)
    formularios = {"form_entrada": form} if prefixo == "entrada" else {"form_ajuste": form}
    return render(request, "estoque/_painel_produto.html", _contexto_ficha(produto, aviso=aviso, **formularios))


@login_required
@require_POST
def entrada(request, pk):
    return _lancar(request, pk, EntradaForm, "entrada", services.registrar_entrada,
                   lambda m: f"Entrada de {m.quantidade} {m.produto.unidade} registrada.")


@login_required
@require_POST
def ajuste(request, pk):
    return _lancar(request, pk, AjusteForm, "ajuste", services.registrar_ajuste,
                   lambda m: f"Ajuste de {m.quantidade:+d} {m.produto.unidade} registrado.")


@login_required
def movimentacoes(request):
    tipo = request.GET.get("tipo", "")
    busca = request.GET.get("q", "").strip()
    lista = MovimentacaoEstoque.objects.select_related("produto", "usuario", "ordem")
    if tipo:
        lista = lista.filter(tipo=tipo)
    if busca:
        lista = lista.filter(Q(produto__nome__icontains=busca) | Q(produto__codigo__icontains=busca)
                             | Q(ordem__numero__icontains=busca) | Q(observacao__icontains=busca))
    pagina = Paginator(lista, 50).get_page(request.GET.get("pagina"))
    return render(request, "estoque/movimentacoes.html", {
        "pagina": pagina, "tipo": tipo, "busca": busca, "tipos": MovimentacaoEstoque.Tipo.choices})
