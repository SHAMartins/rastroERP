from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from seguranca.arquivos import validar_anexo


class OrdemServico(models.Model):
    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        AGENDADA = "AGENDADA", "Agendada"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        PENDENTE = "PENDENTE", "Pendente"
        PAUSADA = "PAUSADA", "Pausada"
        FECHADA = "FECHADA", "Fechada"
        CANCELADA = "CANCELADA", "Cancelada"

    class Prioridade(models.TextChoices):
        BAIXA = "BAIXA", "Baixa"
        MEDIA = "MEDIA", "Media"
        ALTA = "ALTA", "Alta"
        URGENTE = "URGENTE", "Urgente"

    numero = models.CharField("Numero da OS", max_length=20, unique=True, editable=False)
    # Copiado do chamado ao gerar a OS (facilita filtros e a regra "produto do cliente")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, related_name="ordens", editable=False)
    chamado = models.ForeignKey("chamados.Chamado", on_delete=models.PROTECT, related_name="ordens")
    servico = models.ForeignKey("clientes.Servico", null=True, blank=True, on_delete=models.PROTECT)
    titulo = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)
    prioridade = models.CharField(max_length=10, choices=Prioridade.choices, default=Prioridade.MEDIA)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ABERTA)
    responsavel = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="ordens_responsavel", verbose_name="Tecnico responsavel")
    data_abertura = models.DateTimeField(default=timezone.now, editable=False)
    data_agendada = models.DateTimeField(null=True, blank=True)
    data_fechamento = models.DateTimeField(null=True, blank=True, editable=False)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT,
                                   related_name="ordens_criadas", editable=False)

    # Campos acompanhados no historico de alteracoes
    CAMPOS_AUDITADOS = ["titulo", "descricao", "servico", "prioridade",
                        "status", "responsavel", "data_agendada"]

    class Meta:
        ordering = ["-data_abertura"]
        verbose_name = "ordem de servico"
        verbose_name_plural = "ordens de servico"
        permissions = [("operar_qualquer_os", "Operar OS de qualquer tecnico (nao so as atribuidas a si)")]

    def __str__(self):
        return f"OS {self.numero} - {self.titulo}"

    # Endereco e coordenadas vem do chamado (fonte unica de verdade)
    @property
    def endereco(self):
        return self.chamado.endereco

    @property
    def coordenadas(self):
        return self.chamado.coordenadas


class Anexo(models.Model):
    ordem = models.ForeignKey(OrdemServico, on_delete=models.PROTECT, related_name="anexos")
    arquivo = models.FileField(upload_to="anexos/%Y/%m/", validators=[validar_anexo])
    descricao = models.CharField(max_length=150, blank=True)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    enviado_em = models.DateTimeField(auto_now_add=True)

    @property
    def url_download(self):
        return reverse("seguranca:anexo", args=["os", self.pk])


class Comentario(models.Model):
    ordem = models.ForeignKey(OrdemServico, on_delete=models.PROTECT, related_name="comentarios")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    texto = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em"]


class HistoricoAlteracao(models.Model):
    """Trilha de auditoria: quem alterou, quando, qual campo, de que valor para qual."""
    ordem = models.ForeignKey(OrdemServico, on_delete=models.PROTECT, related_name="historico")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    campo = models.CharField(max_length=50)
    valor_anterior = models.TextField(blank=True)
    valor_novo = models.TextField(blank=True)
    alterado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-alterado_em"]
        verbose_name = "historico de alteracao"
        verbose_name_plural = "historico de alteracoes"
