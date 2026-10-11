"""Chamado (na tela: atividade) = o pedido. A execucao fica na OS (app ordens), mostrada dentro dele.

Equivale a Nota de manutencao -> Ordem de manutencao do SAP PM.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from seguranca.arquivos import validar_anexo


class Tipo(models.TextChoices):
    # Manutencao reune incidente, corretiva e preventiva; Instalacao reune ativacao e execucao de servico
    MANUTENCAO = "MANUTENCAO", "Manutencao"
    INSTALACAO = "INSTALACAO", "Instalacao"


class Prioridade(models.TextChoices):
    BAIXA = "BAIXA", "Baixa"
    MEDIA = "MEDIA", "Media"
    ALTA = "ALTA", "Alta"
    URGENTE = "URGENTE", "Urgente"


class PoliticaSLA(models.Model):
    """Prazos de atendimento. Sem cliente = padrao geral; com cliente = contrato daquele cliente."""
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.CASCADE,
                                related_name="politicas_sla", help_text="Vazio = padrao para todos os clientes")
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    prioridade = models.CharField(max_length=10, choices=Prioridade.choices)
    horas_resposta = models.DecimalField("Primeira resposta (horas)", max_digits=6, decimal_places=1)
    horas_solucao = models.DecimalField("Solucao (horas)", max_digits=6, decimal_places=1)

    class Meta:
        verbose_name = "politica de SLA"
        verbose_name_plural = "politicas de SLA"
        ordering = ["cliente__nome", "tipo", "prioridade"]
        constraints = [models.UniqueConstraint(fields=["cliente", "tipo", "prioridade"], nulls_distinct=False,
                                               name="sla_unico_por_cliente_tipo_prioridade")]

    def __str__(self):
        dono = self.cliente or "Padrao"
        return f"{dono} - {self.get_tipo_display()} / {self.get_prioridade_display()}"


class Chamado(models.Model):
    class Impacto(models.TextChoices):
        ALTO = "ALTO", "Alto - varios usuarios ou servico parado"
        MEDIO = "MEDIO", "Medio - servico degradado"
        BAIXO = "BAIXO", "Baixo - um usuario, sem parada"

    class Urgencia(models.TextChoices):
        ALTA = "ALTA", "Alta - precisa de solucao imediata"
        MEDIA = "MEDIA", "Media - pode aguardar algumas horas"
        BAIXA = "BAIXA", "Baixa - pode ser agendado"

    class Status(models.TextChoices):
        NOVO = "NOVO", "Novo (aguardando triagem)"
        EM_ATENDIMENTO = "EM_ATENDIMENTO", "Em atendimento"
        PENDENTE_CLIENTE = "PENDENTE_CLIENTE", "Pendente cliente"
        RESOLVIDO = "RESOLVIDO", "Resolvido"
        CANCELADO = "CANCELADO", "Cancelado"

    class Encerramento(models.TextChoices):
        REMOTO = "REMOTO", "Resolvido remotamente"
        CAMPO = "CAMPO", "Resolvido em campo"
        CONCLUIDO = "CONCLUIDO", "Instalacao/servico concluido"
        SEM_DEFEITO = "SEM_DEFEITO", "Sem defeito constatado"
        CLIENTE = "CLIENTE", "Responsabilidade do cliente"
        TERCEIROS = "TERCEIROS", "Causa externa (terceiros, energia, rompimento)"

    ENCERRADOS = (Status.RESOLVIDO, Status.CANCELADO)

    numero = models.CharField("Numero do chamado", max_length=20, unique=True, editable=False)
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, related_name="chamados")
    titulo = models.CharField(max_length=150)
    # Campos especificos do tipo (definidos em chamados/campos.py), sem texto livre generico
    detalhes = models.JSONField(default=dict, blank=True)

    # Quem pediu
    solicitante_nome = models.CharField("Solicitante", max_length=120)
    solicitante_contato = models.CharField("Contato do solicitante", max_length=120, blank=True)

    # Onde: o endereco fica no proprio chamado (o cliente atende clientes finais com varias unidades)
    cliente_final = models.CharField("Cliente final / unidade", max_length=150, blank=True)
    endereco = models.CharField("Endereco", max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    contato_local = models.CharField("Contato no local", max_length=120, blank=True)
    janela_acesso = models.CharField("Janela de acesso", max_length=120, blank=True,
                                     help_text="Ex.: seg a sex, 8h as 18h")
    ativo = models.CharField("Ativo / circuito", max_length=120, blank=True,
                             help_text="Designacao do circuito, equipamento ou numero de serie")

    # Prioridade = matriz impacto x urgencia (calculada, nunca digitada)
    impacto = models.CharField(max_length=6, choices=Impacto.choices, default=Impacto.MEDIO)
    urgencia = models.CharField("Urgencia", max_length=6, choices=Urgencia.choices, default=Urgencia.MEDIA)
    prioridade = models.CharField(max_length=10, choices=Prioridade.choices, editable=False)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NOVO)
    responsavel = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="chamados_responsavel", verbose_name="Responsavel pela triagem")
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT,
                                   related_name="chamados_criados", editable=False)

    # SLA: prazos calculados na abertura; tempo "pendente cliente" nao conta
    aberto_em = models.DateTimeField(default=timezone.now, editable=False)
    prazo_resposta = models.DateTimeField(null=True, editable=False)
    prazo_solucao = models.DateTimeField(null=True, editable=False)
    primeira_resposta_em = models.DateTimeField(null=True, editable=False)
    resolvido_em = models.DateTimeField(null=True, editable=False)
    pausado_desde = models.DateTimeField(null=True, editable=False)
    tempo_pausado = models.DurationField(default=timedelta, editable=False)

    # Encerramento: sustenta os indicadores (o que mais quebra e por que)
    nota_resolucao = models.TextField("Nota de resolucao", blank=True)
    causa = models.CharField("Causa", max_length=150, blank=True)
    categoria_encerramento = models.CharField("Categoria de encerramento", max_length=12,
                                              choices=Encerramento.choices, blank=True)

    CAMPOS_AUDITADOS = ["tipo", "titulo", "solicitante_nome", "solicitante_contato", "cliente_final",
                        "endereco", "latitude", "longitude", "contato_local", "janela_acesso", "ativo",
                        "impacto", "urgencia", "prioridade", "status", "responsavel",
                        "nota_resolucao", "causa", "categoria_encerramento"]

    class Meta:
        ordering = ["-aberto_em"]
        # Permissoes de negocio (RBAC): distribuidas aos perfis em seguranca/perfis.py
        permissions = [("triar_chamado", "Triar, reclassificar e mudar status de atividades"),
                       ("gerar_os", "Gerar ordens de servico"),
                       ("gerenciar_sla", "Editar prazos de SLA (padrao e contratos)")]

    def __str__(self):
        return f"{self.numero} - {self.titulo}"

    @property
    def coordenadas(self):
        if self.latitude is None or self.longitude is None:
            return None
        return f"{self.latitude}, {self.longitude}"

    @property
    def encerrado(self):
        return self.status in self.ENCERRADOS

    def _pausa_total(self, agora):
        pausa = self.tempo_pausado
        if self.pausado_desde:
            pausa += agora - self.pausado_desde
        return pausa

    @property
    def prazo_solucao_efetivo(self):
        """Prazo de solucao empurrado pelo tempo em que o chamado ficou pendente com o cliente."""
        if not self.prazo_solucao:
            return None
        return self.prazo_solucao + self._pausa_total(timezone.now())

    @property
    def situacao_sla(self):
        """NO_PRAZO, EM_RISCO, ESTOURADO, PAUSADO, CUMPRIDO, VIOLADO ou SEM_SLA."""
        if not self.prazo_solucao or self.status == self.Status.CANCELADO:
            return "SEM_SLA"
        limite = self.prazo_solucao_efetivo
        if self.status == self.Status.RESOLVIDO:
            return "CUMPRIDO" if self.resolvido_em <= limite else "VIOLADO"
        if self.status == self.Status.PENDENTE_CLIENTE:
            return "PAUSADO"
        agora = timezone.now()
        if agora > limite:
            return "ESTOURADO"
        total = (self.prazo_solucao - self.aberto_em).total_seconds()
        consumido = (agora - self.aberto_em - self._pausa_total(agora)).total_seconds()
        return "EM_RISCO" if total and consumido / total >= 0.8 else "NO_PRAZO"

    @property
    def percentual_sla(self):
        """Quanto do prazo de solucao ja foi consumido (0-100), para a barra de progresso."""
        if not self.prazo_solucao:
            return 0
        fim = self.resolvido_em or timezone.now()
        total = (self.prazo_solucao - self.aberto_em).total_seconds()
        consumido = (fim - self.aberto_em - self._pausa_total(fim)).total_seconds()
        return max(0, min(100, round(consumido / total * 100))) if total else 100

    @property
    def resposta_no_prazo(self):
        """True/False quando ja da para saber; None enquanto ainda esta dentro do prazo sem resposta."""
        if not self.prazo_resposta:
            return None
        if self.primeira_resposta_em:
            return self.primeira_resposta_em <= self.prazo_resposta
        return False if timezone.now() > self.prazo_resposta else None


class ComentarioChamado(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.PROTECT, related_name="comentarios")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    texto = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em"]
        verbose_name = "comentario"


class AnexoChamado(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.PROTECT, related_name="anexos")
    arquivo = models.FileField(upload_to="chamados/%Y/%m/", validators=[validar_anexo])
    descricao = models.CharField(max_length=150, blank=True)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "anexo"

    @property
    def nome_arquivo(self):
        return self.arquivo.name.rsplit("/", 1)[-1]

    @property
    def url_download(self):
        return reverse("seguranca:anexo", args=["atividade", self.pk])


class HistoricoChamado(models.Model):
    """Trilha de auditoria do chamado: quem alterou, quando, qual campo, de que valor para qual."""
    chamado = models.ForeignKey(Chamado, on_delete=models.PROTECT, related_name="historico")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    campo = models.CharField(max_length=50)
    valor_anterior = models.TextField(blank=True)
    valor_novo = models.TextField(blank=True)
    alterado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-alterado_em"]
        verbose_name = "historico do chamado"
        verbose_name_plural = "historico dos chamados"
