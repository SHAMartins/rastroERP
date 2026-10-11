"""Cadastros: clientes (com contrato de SLA), servicos e SLA padrao."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from chamados import services as chamados
from chamados.models import Chamado, PoliticaSLA, Prioridade, Tipo
from seguranca.permissoes import exigir

from .forms import ClienteForm, ServicoForm
from .models import Cliente, Servico


def _matriz_sla(cliente, post=None):
    """Linhas tipo x prioridade para a tabela de SLA. No contrato, mostra o padrao como referencia."""
    proprios = {(p.tipo, p.prioridade): p for p in PoliticaSLA.objects.filter(cliente=cliente)}
    padrao = {(p.tipo, p.prioridade): p for p in PoliticaSLA.objects.filter(cliente__isnull=True)} if cliente else {}
    linhas = []
    for tipo, nome_tipo in Tipo.choices:
        celulas = []
        for prioridade, nome_prioridade in Prioridade.choices:
            chave, p, ref = f"{tipo}-{prioridade}", proprios.get((tipo, prioridade)), padrao.get((tipo, prioridade))
            celulas.append({
                "chave": chave, "prioridade": nome_prioridade,
                "resposta": post.get(f"{chave}-resposta", "") if post else (p.horas_resposta if p else ""),
                "solucao": post.get(f"{chave}-solucao", "") if post else (p.horas_solucao if p else ""),
                "ref": ref,
            })
        linhas.append({"tipo": tipo, "nome": nome_tipo, "celulas": celulas})
    return linhas


def _valores_sla(post):
    return {(t, p): (post.get(f"{t}-{p}-resposta", ""), post.get(f"{t}-{p}-solucao", ""))
            for t, _ in Tipo.choices for p, _ in Prioridade.choices}


@login_required
def clientes(request):
    busca = request.GET.get("q", "").strip()
    situacao = request.GET.get("situacao", "ativos")
    lista = Cliente.objects.annotate(
        abertas=Count("chamados", filter=~Q(chamados__status__in=Chamado.ENCERRADOS), distinct=True),
        contrato=Count("politicas_sla", distinct=True)).order_by("nome")
    if situacao == "ativos":
        lista = lista.filter(ativo=True)
    elif situacao == "inativos":
        lista = lista.filter(ativo=False)
    if busca:
        lista = lista.filter(Q(nome__icontains=busca) | Q(documento__icontains=busca) | Q(email__icontains=busca))
    pagina = Paginator(lista, 25).get_page(request.GET.get("pagina"))
    return render(request, "cadastros/clientes.html", {"pagina": pagina, "busca": busca, "situacao": situacao})


@login_required
def cliente_form(request, pk=None):
    cliente = get_object_or_404(Cliente, pk=pk) if pk else None
    permissao = "clientes.change_cliente" if cliente else "clientes.add_cliente"
    pode_editar = request.user.has_perm(permissao)
    if request.method == "POST" or not cliente:
        exigir(request.user, permissao)
    form = ClienteForm(request.POST or None, instance=cliente)
    if not pode_editar:
        for campo in form.fields.values():
            campo.disabled = True
    if request.method == "POST" and form.is_valid():
        novo = form.save()
        messages.success(request, f"Cliente {novo.nome} {'atualizado' if cliente else 'cadastrado'}.")
        return redirect("cadastros:cliente", pk=novo.pk)
    contexto = {"form": form, "cliente": cliente, "pode_editar": pode_editar}
    if cliente:
        contexto.update({
            "sla": _matriz_sla(cliente),
            "servicos": cliente.servicos.all(),
            "atividades": cliente.chamados.exclude(status__in=Chamado.ENCERRADOS).order_by("prazo_solucao")[:8],
        })
    return render(request, "cadastros/cliente.html", contexto)


@login_required
def sla(request, pk=None):
    """Tabela de SLA: do contrato do cliente (pk) ou a padrao (sem pk)."""
    exigir(request.user, "chamados.gerenciar_sla")
    cliente = get_object_or_404(Cliente, pk=pk) if pk else None
    if request.method == "POST":
        try:
            chamados.salvar_tabela_sla(cliente, _valores_sla(request.POST))
        except ValueError as e:
            messages.error(request, str(e))
            return render(request, "cadastros/sla.html", {"cliente": cliente, "sla": _matriz_sla(cliente, request.POST)})
        messages.success(request, "Prazos de SLA salvos. Valem para as atividades abertas daqui em diante.")
        return redirect("cadastros:cliente", pk=pk) if cliente else redirect("cadastros:sla_padrao")
    return render(request, "cadastros/sla.html", {"cliente": cliente, "sla": _matriz_sla(cliente)})


@login_required
def servicos(request, pk=None):
    servico = get_object_or_404(Servico, pk=pk) if pk else None
    if request.method == "POST" or servico:
        exigir(request.user, "clientes.change_servico" if servico else "clientes.add_servico")
    form = ServicoForm(request.POST or None, instance=servico)
    if request.method == "POST" and form.is_valid():
        salvo = form.save()
        messages.success(request, f"Servico {salvo.nome} {'atualizado' if servico else 'cadastrado'}.")
        return redirect("cadastros:servicos")
    lista = Servico.objects.select_related("cliente").annotate(usos=Count("ordemservico"))
    return render(request, "cadastros/servicos.html", {"form": form, "servico": servico, "lista": lista})
