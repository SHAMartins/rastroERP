import re

from django import forms

from ordens.forms import bootstrap

from .models import Cliente, Servico


def formatar_documento(digitos):
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "documento", "email", "telefone", "ativo"]
        labels = {"ativo": "Cliente ativo (pode abrir atividades)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["documento"].widget.attrs["placeholder"] = "CPF ou CNPJ, com ou sem pontuacao"
        bootstrap(self)
        self.fields["ativo"].widget.attrs["class"] = "form-check-input"

    def clean_documento(self):
        # Aceita com ou sem pontuacao e grava sempre no mesmo formato (evita duplicidade disfarcada)
        digitos = re.sub(r"\D", "", self.cleaned_data["documento"])
        if len(digitos) not in (11, 14):
            raise forms.ValidationError("Informe um CPF (11 digitos) ou CNPJ (14 digitos).")
        documento = formatar_documento(digitos)
        if Cliente.objects.filter(documento=documento).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ja existe um cliente com este documento.")
        return documento


class ServicoForm(forms.ModelForm):
    class Meta:
        model = Servico
        fields = ["nome", "descricao", "cliente"]
        widgets = {"descricao": forms.Textarea(attrs={"rows": 2})}
        help_texts = {"cliente": "Deixe vazio para um servico disponivel a todos os clientes."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].empty_label = "Todos os clientes (servico geral)"
        bootstrap(self)
