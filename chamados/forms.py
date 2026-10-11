from django import forms
from django.contrib.auth import get_user_model

from clientes.models import Cliente
from ordens.forms import bootstrap, servicos_do_cliente
from ordens.models import OrdemServico

from seguranca.arquivos import AJUDA_ANEXO, validar_anexo

from . import campos
from .models import Chamado, Tipo


PREFIXO = "d_"   # campos especificos do tipo: d_<nome>


def campo_django(c):
    """Converte a definicao de chamados/campos.py em um campo de formulario Django."""
    attrs = {"placeholder": c.placeholder} if c.placeholder else {}
    comum = {"label": c.rotulo, "required": c.obrigatorio, "help_text": c.ajuda}
    if c.tipo == campos.TEXTO_LONGO:
        return forms.CharField(widget=forms.Textarea(attrs={"rows": 3, **attrs}), **comum)
    if c.tipo == campos.DATA:
        return forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), **comum)
    if c.tipo == campos.DATA_HORA:
        return forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"},
                                                              format="%Y-%m-%dT%H:%M"), **comum)
    if c.tipo == campos.ESCOLHA:
        return forms.ChoiceField(choices=[("", "Selecione")] + list(c.opcoes), **comum)
    return forms.CharField(max_length=255, widget=forms.TextInput(attrs=attrs), **comum)


class NovoChamadoForm(forms.ModelForm):
    class Meta:
        model = Chamado
        fields = ["tipo", "cliente", "titulo",
                  "solicitante_nome", "solicitante_contato",
                  "cliente_final", "endereco", "latitude", "longitude", "contato_local", "janela_acesso", "ativo",
                  "impacto", "urgencia", "responsavel"]

    def __init__(self, *args, tipo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.filter(ativo=True)
        self.fields["responsavel"].queryset = get_user_model().objects.filter(is_active=True)
        self.fields["tipo"].choices = [("", "Selecione o tipo")] + list(Tipo.choices)
        # Cada tipo de chamado tem o seu proprio conjunto de campos
        self.tipo = tipo or self.data.get("tipo") or self.initial.get("tipo")
        self.definicoes = campos.campos_do_tipo(self.tipo)
        for c in self.definicoes:
            self.fields[PREFIXO + c.nome] = campo_django(c)
        bootstrap(self)

    @property
    def campos_tipo(self):
        """[(definicao, campo do form)] para o template montar o bloco do tipo."""
        return [(c, self[PREFIXO + c.nome]) for c in self.definicoes]

    def clean(self):
        dados = super().clean()
        # Ativo e obrigatorio so quando muda a triagem (algo que parou ou quebrou)
        if dados.get("tipo") == "MANUTENCAO" and not dados.get("ativo", "").strip():
            self.add_error("ativo", "Obrigatorio para manutencao.")
        return dados

    def dados_chamado(self):
        """Campos do model + detalhes do tipo, prontos para services.abrir_chamado."""
        dados = {k: v for k, v in self.cleaned_data.items() if not k.startswith(PREFIXO)}
        dados["detalhes"] = {c.nome: self.cleaned_data.get(PREFIXO + c.nome) for c in self.definicoes}
        return dados


class StatusChamadoForm(forms.Form):
    status = forms.ChoiceField(choices=Chamado.Status.choices)
    nota_resolucao = forms.CharField(label="Nota de resolucao", required=False,
                                     widget=forms.Textarea(attrs={"rows": 3}))
    causa = forms.CharField(label="Causa", required=False, max_length=150)
    categoria_encerramento = forms.ChoiceField(label="Categoria de encerramento", required=False,
                                               choices=[("", "---------")] + list(Chamado.Encerramento.choices))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self)


class GerarOSForm(forms.ModelForm):
    class Meta:
        model = OrdemServico
        fields = ["titulo", "descricao", "servico", "prioridade", "responsavel", "data_agendada"]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 3}),
            "data_agendada": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, chamado, **kwargs):
        kwargs.setdefault("initial", {"titulo": chamado.titulo, "prioridade": chamado.prioridade})
        super().__init__(*args, **kwargs)
        self.fields["servico"].queryset = servicos_do_cliente(chamado.cliente_id)
        self.fields["responsavel"].queryset = get_user_model().objects.filter(is_active=True)
        self.fields["descricao"].help_text = "Instrucoes para o tecnico. Endereco e contato vem do chamado."
        bootstrap(self)


class AnexoForm(forms.Form):
    arquivo = forms.FileField(validators=[validar_anexo], help_text=AJUDA_ANEXO)
    descricao = forms.CharField(required=False, max_length=150, widget=forms.TextInput(
        attrs={"placeholder": "Descricao (opcional)"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self)
