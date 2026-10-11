from django.contrib import messages
from django.contrib.auth import get_user_model, views as auth
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy

from chamados.models import AnexoChamado
from ordens.models import Anexo

from . import bloqueio
from .arquivos import resposta_download
from .eventos import registrar
from .forms import LoginForm, SenhaForm, UsuarioForm
from .models import EventoSeguranca
from .perfis import PERFIS, perfil_de

User = get_user_model()


class Entrar(auth.LoginView):
    template_name = "seguranca/entrar.html"
    form_class = LoginForm
    redirect_authenticated_user = True


class TrocarSenha(auth.PasswordChangeView):
    template_name = "seguranca/senha.html"
    form_class = SenhaForm
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        resposta = super().form_valid(form)
        registrar(EventoSeguranca.Tipo.SENHA_ALTERADA, self.request.user, ip=bloqueio.ip_do_request(self.request))
        messages.success(self.request, "Senha alterada.")
        return resposta


@login_required
def baixar_anexo(request, origem, pk):
    """Anexos so saem por aqui (com login). /media/ nao e publico."""
    modelo = {"atividade": AnexoChamado, "os": Anexo}.get(origem)
    if modelo is None:
        raise PermissionDenied
    return resposta_download(get_object_or_404(modelo, pk=pk).arquivo)


@login_required
@permission_required("auth.change_user", raise_exception=True)
def usuarios(request):
    lista = User.objects.prefetch_related("groups").order_by("-is_active", "username")
    for u in lista:
        u.perfil = perfil_de(u)
    return render(request, "seguranca/usuarios.html", {"lista": lista})


@login_required
@permission_required("auth.change_user", raise_exception=True)
def usuario_form(request, pk=None):
    usuario = get_object_or_404(User, pk=pk) if pk else None
    if usuario and usuario.is_superuser and not request.user.is_superuser:
        raise PermissionDenied("So um superusuario pode alterar outro superusuario.")
    if not usuario and not request.user.has_perm("auth.add_user"):
        raise PermissionDenied
    form = UsuarioForm(request.POST or None, instance=usuario, editor=request.user)
    if request.method == "POST" and form.is_valid():
        salvo = form.save()
        if not usuario:
            registrar(EventoSeguranca.Tipo.USUARIO_CRIADO, salvo, detalhe=f"Perfil {form.cleaned_data['perfil']}")
        elif form.cleaned_data.get("senha"):
            registrar(EventoSeguranca.Tipo.SENHA_ALTERADA, salvo, detalhe="Senha redefinida pelo administrador")
        messages.success(request, f"Usuario {salvo.username} salvo.")
        return redirect("seguranca:usuarios")
    return render(request, "seguranca/usuario.html", {"form": form, "usuario": usuario, "perfis": PERFIS})


@login_required
@permission_required("seguranca.view_eventoseguranca", raise_exception=True)
def eventos(request):
    tipo = request.GET.get("tipo", "")
    busca = request.GET.get("q", "").strip()
    lista = EventoSeguranca.objects.select_related("usuario", "autor")
    if tipo:
        lista = lista.filter(tipo=tipo)
    if busca:
        lista = lista.filter(nome_usuario__icontains=busca) | lista.filter(ip__icontains=busca)
    pagina = Paginator(lista, 50).get_page(request.GET.get("pagina"))
    return render(request, "seguranca/eventos.html", {"pagina": pagina, "tipo": tipo, "busca": busca,
                                                      "tipos": EventoSeguranca.Tipo.choices})


def acesso_negado(request, exception=None):
    """handler403: pagina propria + registro no log de seguranca."""
    usuario = request.user if request.user.is_authenticated else None
    registrar(EventoSeguranca.Tipo.ACESSO_NEGADO, usuario, ip=bloqueio.ip_do_request(request),
              detalhe=f"{request.method} {request.path}")
    motivo = str(exception) if exception and str(exception) else "Seu perfil nao permite esta acao."
    return render(request, "403.html", {"motivo": motivo}, status=403)
