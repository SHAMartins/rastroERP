from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum


class Produto(models.Model):
    """Sem cliente = estoque geral da empresa; com cliente = material reservado/de propriedade do cliente."""
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="produtos")
    codigo = models.CharField("Código", max_length=60, unique=True,
                              help_text="Código interno ou de barras (EAN) do produto")
    nome = models.CharField(max_length=150)
    tipo = models.CharField(max_length=60, blank=True, help_text="Ex.: ONT, roteador, cabo, conector")
    modelo = models.CharField(max_length=100, blank=True)
    controla_serie = models.BooleanField("Controla número de série", default=False,
                                         help_text="Cada unidade tem o seu número de série (equipamentos)")
    unidade = models.CharField(max_length=10, default="un")
    estoque_minimo = models.PositiveIntegerField("Estoque mínimo", default=0)
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
        SAIDA_OS = "SAIDA_OS", "Saída (uso em OS)"
        AJUSTE = "AJUSTE", "Ajuste"
        ESTORNO = "ESTORNO", "Estorno"

    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="movimentacoes")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    quantidade = models.IntegerField()
    ordem = models.ForeignKey("ordens.OrdemServico", null=True, blank=True, on_delete=models.PROTECT,
                              related_name="movimentacoes")
    observacao = models.CharField("Observação", max_length=255, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, verbose_name="Usuário")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "movimentação de estoque"
        verbose_name_plural = "movimentações de estoque"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Movimentações são imutáveis. Registre um ajuste.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Movimentações não podem ser apagadas.")


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
    numero_serie = models.CharField("Número de série", max_length=100)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.EM_ESTOQUE)
    entrada = models.ForeignKey(MovimentacaoEstoque, on_delete=models.PROTECT, related_name="itens_entrada")
    saida = models.ForeignKey(MovimentacaoEstoque, null=True, blank=True, on_delete=models.PROTECT, verbose_name="Saída",
                              related_name="itens_saida")

    class Meta:
        ordering = ["numero_serie"]
        verbose_name = "item com número de série"
        verbose_name_plural = "itens com número de série"
        constraints = [models.UniqueConstraint(fields=["produto", "numero_serie"], name="serie_unica_por_produto")]

    def __str__(self):
        return f"{self.produto.nome} - SN {self.numero_serie}"


class TarefaReposicao(models.Model):
    """Tarefa criada sozinha quando o saldo de um produto chega ao estoque minimo.

    Integracao estoque -> gestao de tarefas: a baixa (OS ou ajuste) que derruba o saldo abre a tarefa;
    a entrada que repoe o saldo acima do minimo a conclui. So existe uma tarefa aberta por produto.
    """

    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        CONCLUIDA = "CONCLUIDA", "Concluída"
        CANCELADA = "CANCELADA", "Cancelada"

    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="reposicoes")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTA)
    saldo_na_abertura = models.IntegerField()
    minimo_na_abertura = models.PositiveIntegerField("Mínimo na abertura")
    quantidade_sugerida = models.PositiveIntegerField(help_text="Quanto comprar/repor para voltar ao nível ideal")
    origem = models.ForeignKey(MovimentacaoEstoque, on_delete=models.PROTECT, related_name="reposicoes_abertas",
                               help_text="Movimentação que levou o saldo ao mínimo")
    responsavel = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    verbose_name="Responsável",
                                    related_name="reposicoes")
    criada_em = models.DateTimeField(auto_now_add=True)
    encerrada_em = models.DateTimeField(null=True, blank=True)
    conclusao = models.ForeignKey(MovimentacaoEstoque, null=True, blank=True, on_delete=models.PROTECT, verbose_name="Conclusão",
                                  related_name="reposicoes_concluidas", help_text="Entrada que repôs o saldo")
    motivo_cancelamento = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-criada_em"]
        verbose_name = "tarefa de reposição"
        verbose_name_plural = "tarefas de reposição"
        constraints = [models.UniqueConstraint(fields=["produto"], condition=models.Q(status="ABERTA"),
                                               name="uma_reposicao_aberta_por_produto")]

    def __str__(self):
        return f"Repor {self.quantidade_sugerida} {self.produto.unidade} de {self.produto.nome}"
