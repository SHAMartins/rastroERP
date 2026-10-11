from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum


class Produto(models.Model):
    """Sem cliente = estoque geral da empresa; com cliente = material reservado/de propriedade do cliente."""
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="produtos")
    codigo = models.CharField("Codigo", max_length=60, unique=True,
                              help_text="Codigo interno ou de barras (EAN) do produto")
    nome = models.CharField(max_length=150)
    tipo = models.CharField(max_length=60, blank=True, help_text="Ex.: ONT, roteador, cabo, conector")
    modelo = models.CharField(max_length=100, blank=True)
    controla_serie = models.BooleanField("Controla numero de serie", default=False,
                                         help_text="Cada unidade tem o seu numero de serie (equipamentos)")
    unidade = models.CharField(max_length=10, default="un")
    estoque_minimo = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        permissions = [("movimentar_estoque", "Registrar entradas e ajustes de estoque")]

    def __str__(self):
        return f"{self.codigo} - {self.nome}"

    @property
    def saldo(self):
        """Saldo = soma do historico de movimentacoes (livro-razao)."""
        return self.movimentacoes.aggregate(t=Sum("quantidade"))["t"] or 0

    @property
    def abaixo_do_minimo(self):
        return self.saldo <= self.estoque_minimo


class MovimentacaoEstoque(models.Model):
    """Registro imutavel. Entradas positivas, saidas negativas."""

    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA_OS = "SAIDA_OS", "Saida (uso em OS)"
        AJUSTE = "AJUSTE", "Ajuste"
        ESTORNO = "ESTORNO", "Estorno"

    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="movimentacoes")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    quantidade = models.IntegerField()
    ordem = models.ForeignKey("ordens.OrdemServico", null=True, blank=True, on_delete=models.PROTECT,
                              related_name="movimentacoes")
    observacao = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "movimentacao de estoque"
        verbose_name_plural = "movimentacoes de estoque"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Movimentacoes sao imutaveis. Registre um ajuste.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Movimentacoes nao podem ser apagadas.")


class ItemSerie(models.Model):
    """Uma unidade fisica de um produto que controla numero de serie.

    O saldo continua vindo das movimentacoes; o item diz QUAL unidade entrou e para onde foi
    (entrada -> movimentacao de entrada; saida -> movimentacao de saida, que aponta para a OS).
    """

    class Status(models.TextChoices):
        EM_ESTOQUE = "EM_ESTOQUE", "Em estoque"
        UTILIZADO = "UTILIZADO", "Utilizado em OS"
        BAIXADO = "BAIXADO", "Baixado (perda/defeito)"

    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="itens")
    numero_serie = models.CharField("Numero de serie", max_length=100)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.EM_ESTOQUE)
    entrada = models.ForeignKey(MovimentacaoEstoque, on_delete=models.PROTECT, related_name="itens_entrada")
    saida = models.ForeignKey(MovimentacaoEstoque, null=True, blank=True, on_delete=models.PROTECT,
                              related_name="itens_saida")

    class Meta:
        ordering = ["numero_serie"]
        verbose_name = "item com numero de serie"
        verbose_name_plural = "itens com numero de serie"
        constraints = [models.UniqueConstraint(fields=["produto", "numero_serie"], name="serie_unica_por_produto")]

    def __str__(self):
        return f"{self.produto.nome} - SN {self.numero_serie}"
