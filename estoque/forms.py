from django import forms

from ordens.forms import bootstrap

from .models import Produto

SERIES_AJUDA = "Um por linha. Com leitor USB, cada leitura ja pula para a proxima linha."


def campo_series(rotulo="Numeros de serie"):
    return forms.CharField(label=rotulo, required=False, help_text=SERIES_AJUDA,
                           widget=forms.Textarea(attrs={"rows": 3, "data-leitor": "anexar",
                                                        "placeholder": "Leia ou digite os numeros de serie"}))


class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = ["codigo", "nome", "tipo", "modelo", "unidade", "estoque_minimo", "cliente",
                  "controla_serie", "ativo"]
        labels = {"estoque_minimo": "Estoque minimo", "cliente": "Material do cliente", "ativo": "Produto ativo"}
        help_texts = {"cliente": "Deixe vazio para material da empresa. Material de cliente so pode ir para OS dele.",
                      "estoque_minimo": "Abaixo disso o produto aparece no alerta de reposicao."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].empty_label = "Estoque da empresa"
        self.fields["unidade"].widget.attrs["placeholder"] = "un, m, cx, rolo"
        self.fields["codigo"].widget.attrs.update({"data-leitor": "substituir", "autofocus": True,
                                                   "placeholder": "Digite ou leia o codigo de barras"})
        self.fields["tipo"].widget.attrs["list"] = "tipos-produto"     # sugere os tipos ja usados
        bootstrap(self)
        for nome in ("ativo", "controla_serie"):
            self.fields[nome].widget.attrs["class"] = "form-check-input"

    def clean_codigo(self):
        return self.cleaned_data["codigo"].strip()

    def clean_controla_serie(self):
        novo = self.cleaned_data["controla_serie"]
        produto = self.instance
        if produto.pk and novo != produto.controla_serie and produto.saldo != 0:
            raise forms.ValidationError("So da para mudar o controle de numero de serie com o saldo zerado.")
        return novo

    def clean(self):
        dados = super().clean()
        if dados.get("controla_serie") and dados.get("unidade", "un") != "un":
            self.add_error("unidade", "Produto com numero de serie e controlado por unidade (un).")
        return dados


class EntradaForm(forms.Form):
    quantidade = forms.IntegerField(min_value=1, label="Quantidade", required=False)
    numeros_serie = campo_series()
    observacao = forms.CharField(label="Origem / documento", required=False, max_length=255,
                                 widget=forms.TextInput(attrs={"placeholder": "NF 1234, devolucao, compra"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self)

    def clean(self):
        dados = super().clean()
        if not dados.get("quantidade") and not (dados.get("numeros_serie") or "").strip():
            raise forms.ValidationError("Informe a quantidade ou os numeros de serie.")
        return dados


class AjusteForm(forms.Form):
    quantidade = forms.IntegerField(label="Diferenca", help_text="Positivo soma, negativo tira. Ex.: -2")
    numeros_serie = campo_series("Numeros de serie (se o produto tiver)")
    observacao = forms.CharField(label="Justificativa", max_length=255,
                                 widget=forms.TextInput(attrs={"placeholder": "Inventario, perda, avaria"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self)

    def clean_quantidade(self):
        if self.cleaned_data["quantidade"] == 0:
            raise forms.ValidationError("Use + para somar ou - para tirar.")
        return self.cleaned_data["quantidade"]
