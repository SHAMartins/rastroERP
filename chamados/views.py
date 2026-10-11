"""Telas das atividades (chamado + suas OSs na mesma tela). Toda regra passa por services.py."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import F, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from clientes.models import Cliente
from ordens.forms import ComentarioForm, MaterialForm, StatusForm
from ordens.models import OrdemServico
from ordens.views import eventos_da_os, prefixo
from seguranca.permissoes import exigir, pode_operar_os

from . import services
from .forms import AnexoForm, GerarOSForm, NovoChamadoForm, StatusChamadoForm
from .campos import TIPOS, detalhes_legiveis, rotulo
from .models import Chamado, Tipo

ROTULOS_HISTORICO = {"criacao": "Abertura", "os": "Ordem de servico"}


@login_required
def lista(request):
    chamados = Chamado.objects.select_related("cliente", "responsavel").prefetch_related(
        Prefetch("ordens", queryset=OrdemServico.objects.select_related("responsavel")))
    visao = request.GET.get("visao", "abertos")
    status = request.GET.get("status", "")
    tipo = request.GET.get("tipo", "")
    busca = request.GET.get("q", "").strip()
    if visao == "abertos" and not status:
        # Fila de trabalho: so o que esta em aberto, quem vence primeiro aparece primeiro
        chamados = chamados.exclude(status__in=Chamado.ENCERRADOS).order_by(
            F("prazo_solucao").asc(nulls_last=True))
    if status:
        chamados = chamados.filter(status=status)
    if tipo:
        chamados = chamados.filter(tipo=tipo)
    minhas = request.GET.get("minhas") == "1"
    if minhas:   # atividades com OS em aberto atribuida a mim (agenda do tecnico)
        chamados = chamados.filter(ordens__responsavel=request.user).exclude(
            ordens__status__in=["FECHADA", "CANCELADA"]).distinct()
    if busca:
        chamados = chamados.filter(Q(numero__icontains=busca) | Q(titulo__icontains=busca)
                                   | Q(cliente__nome__icontains=busca) | Q(cliente_final__icontains=busca)
                                   | Q(ativo__icontains=busca) | Q(endereco__icontains=busca)
                                   | Q(ordens__numero__icontains=busca)).distinct()
    pagina = Paginator(chamados, 25).get_page(request.GET.get("pagina"))
    return render(request, "chamados/lista.html", {
        "pagina": pagina, "visao": visao, "status": status, "tipo": tipo, "busca": busca, "minhas": minhas,
        "status_choices": Chamado.Status.choices, "tipo_choices": Tipo.choices})


@login_required
@permission_required("chamados.add_chamado", raise_exception=True)
def novo(request):
    form = NovoChamadoForm(request.POST or None, initial={"cliente": request.GET.get("cliente")})
    if request.method == "POST" and form.is_valid():
        try:
            chamado = services.abrir_chamado(request.user, **form.dados_chamado())
        except ValueError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, f"Atividade {chamado.numero} aberta.")
            return redirect("chamados:detalhe", pk=chamado.pk)   # Post/Redirect/Get
    titulos = {tipo: d["titulo"] for tipo, d in TIPOS.items()}
    return render(request, "chamados/novo.html", {"form": form, "titulos": titulos})


@login_required
def campos_tipo(request):
    """HTMX: troca o bloco de campos especificos quando o usuario escolhe outro tipo."""
    return render(request, "chamados/_campos_tipo.html", {"form": NovoChamadoForm(tipo=request.GET.get("tipo"))})


@login_required
def previa_sla(request):
    """HTMX: mostra a prioridade calculada e os prazos de SLA antes de salvar."""
    g = request.GET
    contexto = {}
    if g.get("impacto") and g.get("urgencia"):
        prioridade = services.calcular_prioridade(g["impacto"], g["urgencia"])
        cliente = Cliente.objects.filter(pk=g.get("cliente")).first() if g.get("cliente", "").isdigit() else None
        contexto = {"prioridade": prioridade, "prioridade_nome": prioridade.label,
                    "politica": services.politica_sla(cliente, g.get("tipo"), prioridade) if g.get("tipo") else None,
                    "tem_tipo": bool(g.get("tipo"))}
    return render(request, "chamados/_previa_sla.html", contexto)


def _linha_do_tempo(chamado):
    itens = [{"data": c.criado_em, "usuario": c.autor, "tipo": "comentario", "texto": c.texto}
             for c in chamado.comentarios.select_related("autor")]
    for h in chamado.historico.select_related("usuario"):
        if h.campo.startswith("detalhe."):
            nome = rotulo(chamado.tipo, h.campo.removeprefix("detalhe."))
        else:
            nome = ROTULOS_HISTORICO.get(h.campo) or Chamado._meta.get_field(h.campo).verbose_name.capitalize()
        itens.append({"data": h.alterado_em, "usuario": h.usuario, "tipo": h.campo, "campo": nome,
                      "antes": h.valor_anterior, "depois": h.valor_novo})
    for ordem in chamado.ordens.all():          # a execucao aparece na mesma linha do tempo
        itens += eventos_da_os(ordem)
    return sorted(itens, key=lambda i: i["data"], reverse=True)


def _ordens_com_formularios(chamado, usuario):
    """OSs da atividade, cada uma com seus materiais e formularios (prefixados para nao colidir).

    Formularios so aparecem para quem pode operar a OS; a view da OS confere de novo no back-end."""
    ordens = list(chamado.ordens.select_related("responsavel", "servico").order_by("data_abertura"))
    for o in ordens:
        o.encerrada = o.status in ("FECHADA", "CANCELADA")
        o.pode_operar = pode_operar_os(usuario, o)
        o.materiais = list(o.movimentacoes.select_related("produto", "usuario").prefetch_related("itens_saida"))
        for m in o.materiais:
            m.qtd_usada = -m.quantidade  # saidas sao gravadas negativas no livro-razao
        o.form_status = StatusForm(initial={"status": o.status}, prefix=prefixo(o))
        o.form_material = None if o.encerrada else MaterialForm(ordem=o, prefix=prefixo(o))
    return ordens


@login_required
def detalhe(request, pk):
    chamado = get_object_or_404(Chamado.objects.select_related("cliente", "responsavel", "criado_por"), pk=pk)
    return render(request, "chamados/detalhe.html", {
        "chamado": chamado,
        "detalhes": detalhes_legiveis(chamado),
        "linha_do_tempo": _linha_do_tempo(chamado),
        "ordens": _ordens_com_formularios(chamado, request.user),
        "anexos": chamado.anexos.select_related("enviado_por"),
        "form_comentario": ComentarioForm(),
        "form_status": StatusChamadoForm(initial={"status": chamado.status}),
        "form_os": None if chamado.encerrado or not request.user.has_perm("chamados.gerar_os")
        else GerarOSForm(chamado=chamado, prefix="nova_os"),
        "form_anexo": AnexoForm(prefix="anexo"),
    })


def _erros(form):
    return " ".join(f"{form.fields[c].label if c in form.fields else ''}: {', '.join(e)}".strip(": ")
                    for c, e in form.errors.items())


@login_required
@require_POST
def comentar(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)
    form = ComentarioForm(request.POST)
    try:
        if not form.is_valid():
            raise ValueError("Escreva o comentario antes de enviar.")
        services.comentar(chamado, request.user, form.cleaned_data["texto"])
        messages.success(request, "Comentario adicionado.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("chamados:detalhe", pk=pk)


@login_required
@require_POST
def alterar_status(request, pk):
    exigir(request.user, "chamados.triar_chamado")
    chamado = get_object_or_404(Chamado, pk=pk)
    form = StatusChamadoForm(request.POST)
    try:
        if not form.is_valid():
            raise ValueError(_erros(form))
        dados = {"status": form.cleaned_data["status"]}
        if dados["status"] == Chamado.Status.RESOLVIDO:
            dados.update({c: form.cleaned_data[c] for c in ("nota_resolucao", "causa", "categoria_encerramento")})
        services.atualizar_chamado(chamado, request.user, **dados)
        messages.success(request, "Status da atividade atualizado.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("chamados:detalhe", pk=pk)


@login_required
@require_POST
def gerar_os(request, pk):
    exigir(request.user, "chamados.gerar_os")
    chamado = get_object_or_404(Chamado, pk=pk)
    form = GerarOSForm(request.POST, chamado=chamado, prefix="nova_os")
    try:
        if not form.is_valid():
            raise ValueError(_erros(form))
        ordem = services.gerar_os(chamado, request.user, **form.cleaned_data)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("chamados:detalhe", pk=pk)
    messages.success(request, f"OS {ordem.numero} gerada.")
    return redirect("ordens:detalhe", pk=ordem.pk)   # leva para a OS dentro da atividade


@login_required
@require_POST
def anexar(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)
    form = AnexoForm(request.POST, request.FILES, prefix="anexo")
    if form.is_valid():
        services.anexar(chamado, request.user, form.cleaned_data["arquivo"], form.cleaned_data["descricao"])
        messages.success(request, "Anexo enviado.")
    else:
        messages.error(request, " ".join(form.errors.get("arquivo", ["Escolha um arquivo para anexar."])))
    return redirect("chamados:detalhe", pk=pk)
