from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from ordens.forms import bootstrap

from . import bloqueio
from .perfis import ADMINISTRADOR, DESCRICOES, PERFIS

User = get_user_model()


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        # Mensagem unica: nao revela se o usuario existe
        "invalid_login": "Usuario ou senha incorretos.",
        "bloqueado": "Muitas tentativas de login. Aguarde alguns minutos e tente de novo.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self)
        self.fields["username"].widget.attrs.update({"autocomplete": "username", "autofocus": True})
        self.fields["password"].widget.attrs["autocomplete"] = "current-password"

    def clean(self):
        nome = self.cleaned_data.get("username")
        if nome and bloqueio.bloqueado(nome, bloqueio.ip_do_request(self.request)):
            # avisa o motivo; a tentativa ainda passa pelo authenticate() para ficar registrada
            try:
                super().clean()
            except forms.ValidationError:
                pass
            raise forms.ValidationError(self.error_messages["bloqueado"], code="bloqueado")
        return super().clean()


class SenhaForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self)


class UsuarioForm(forms.ModelForm):
    perfil = forms.ChoiceField(choices=[(p, f"{p} - {DESCRICOES[p]}") for p in PERFIS])
    senha = forms.CharField(label="Senha", required=False, strip=False,
                            widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    senha2 = forms.CharField(label="Confirme a senha", required=False, strip=False,
                             widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {"username": "Usuario (login)", "is_active": "Ativo (pode entrar no sistema)"}
        help_texts = {"username": ""}

    def __init__(self, *args, editor, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        if self.instance.pk:
            self.fields["perfil"].initial = (self.instance.groups.values_list("name", flat=True).first()
                                             or (ADMINISTRADOR if self.instance.is_superuser else None))
            self.fields["senha"].help_text = "Deixe em branco para manter a senha atual."
        else:
            self.fields["senha"].required = self.fields["senha2"].required = True
        self.fields["senha"].help_text = (self.fields["senha"].help_text + " "
                                          + password_validation.password_validators_help_text_html()).strip()
        bootstrap(self)
        self.fields["is_active"].widget.attrs["class"] = "form-check-input"

    def clean(self):
        dados = super().clean()
        senha, senha2 = dados.get("senha"), dados.get("senha2")
        if senha or senha2:
            if senha != senha2:
                self.add_error("senha2", "As senhas nao conferem.")
            else:
                usuario = self.instance if self.instance.pk else User(username=dados.get("username", ""),
                                                                     email=dados.get("email", ""))
                try:
                    password_validation.validate_password(senha, usuario)
                except forms.ValidationError as e:
                    self.add_error("senha", e)
        # Evita o administrador se trancar para fora do sistema
        if self.instance.pk == self.editor.pk:
            if not dados.get("is_active"):
                self.add_error("is_active", "Voce nao pode desativar a si mesmo.")
            if dados.get("perfil") != ADMINISTRADOR and not self.instance.is_superuser:
                self.add_error("perfil", "Voce nao pode tirar o seu proprio perfil de Administrador.")
        return dados

    def save(self, commit=True):
        usuario = super().save(commit=False)
        perfil = self.cleaned_data["perfil"]
        usuario.is_staff = perfil == ADMINISTRADOR or usuario.is_superuser    # so admin entra no /admin/
        if self.cleaned_data.get("senha"):
            usuario.set_password(self.cleaned_data["senha"])
        usuario.save()
        from django.contrib.auth.models import Group
        usuario.groups.set([Group.objects.get(name=perfil)])
        return usuario
