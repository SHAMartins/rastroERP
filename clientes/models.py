from django.db import models


class Cliente(models.Model):
    nome = models.CharField(max_length=150)
    documento = models.CharField("CPF/CNPJ", max_length=18, unique=True)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Servico(models.Model):
    """Catalogo de servicos/atividades. Sem cliente = servico geral; com cliente = especifico dele."""
    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.PROTECT, related_name="servicos")
    nome = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "servico"

    def __str__(self):
        return self.nome
