from django import forms
from django.db.models import Q

from clientes.models import Servico
from estoque.models import Produto

from .models import OrdemServico


def bootstrap(form):
    for campo in form.fields.values():
        classe = "form-select" if isinstance(campo.widget, forms.Select) else "form-control"
        campo.widget.attrs.setdefault("class", classe)


class ComentarioForm(forms.Form):
    texto = forms.CharField(label="Comentario", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self)


class StatusForm(forms.Form):
    status = forms.ChoiceField(choices=OrdemServico.Status.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self)


class ProdutoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, p):
        serie = " - informe o no de serie" if p.controla_serie else ""
        return f"{p.nome} (saldo {p.saldo} {p.unidade}){serie}"


class MaterialForm(forms.Form):
    produto = ProdutoChoiceField(queryset=Produto.objects.none())
    quantidade = forms.IntegerField(min_value=1, initial=1, required=False)
    numeros_serie = forms.CharField(required=False, label="No de serie", widget=forms.TextInput(attrs={
        "data-leitor": "anexar-virgula", "placeholder": "No de serie (equipamentos)"}))

    def __init__(self, *args, ordem, **kwargs):
        super().__init__(*args, **kwargs)
        # Produto geral ou do proprio cliente da OS
        self.fields["produto"].queryset = Produto.objects.filter(ativo=True).filter(
            Q(cliente__isnull=True) | Q(cliente_id=ordem.cliente_id))
        bootstrap(self)


def servicos_do_cliente(cliente_id):
    return Servico.objects.filter(Q(cliente__isnull=True) | Q(cliente_id=cliente_id))
