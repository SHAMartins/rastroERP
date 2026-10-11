from django.contrib import admin

from chamados.models import PoliticaSLA

from .models import Cliente, Servico


class PoliticaSLAInline(admin.TabularInline):
    """Contrato de SLA do cliente. Combinacoes nao cadastradas usam o SLA padrao."""
    model = PoliticaSLA
    extra = 0
    verbose_name_plural = "SLA do contrato (vazio = usa o SLA padrao)"


class ServicoInline(admin.TabularInline):
    model = Servico
    extra = 0


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "documento", "telefone", "ativo")
    search_fields = ("nome", "documento")
    inlines = [ServicoInline, PoliticaSLAInline]


@admin.register(Servico)
class ServicoAdmin(admin.ModelAdmin):
    list_display = ("nome", "cliente")
    list_filter = ("cliente",)
