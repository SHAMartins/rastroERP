from django.contrib import admin, messages

from . import services
from .models import AnexoChamado, Chamado, ComentarioChamado, HistoricoChamado, PoliticaSLA


@admin.register(PoliticaSLA)
class PoliticaSLAAdmin(admin.ModelAdmin):
    list_display = ("cliente_ou_padrao", "tipo", "prioridade", "horas_resposta", "horas_solucao")
    list_filter = ("tipo", "prioridade", "cliente")
    list_editable = ("horas_resposta", "horas_solucao")

    @admin.display(description="Cliente", ordering="cliente__nome")
    def cliente_ou_padrao(self, obj):
        return obj.cliente or "Padrao (todos os clientes)"


class SomenteLeitura(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ComentarioInline(SomenteLeitura):
    model = ComentarioChamado
    fields = readonly_fields = ("criado_em", "autor", "texto")


class AnexoInline(SomenteLeitura):
    model = AnexoChamado
    fields = readonly_fields = ("enviado_em", "enviado_por", "arquivo", "descricao")


class HistoricoInline(SomenteLeitura):
    model = HistoricoChamado
    fields = readonly_fields = ("alterado_em", "usuario", "campo", "valor_anterior", "valor_novo")


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    list_display = ("numero", "tipo", "titulo", "cliente", "prioridade", "status", "aberto_em", "prazo_solucao")
    list_filter = ("status", "tipo", "prioridade", "cliente")
    search_fields = ("numero", "titulo", "cliente_final", "ativo", "endereco")
    readonly_fields = ("numero", "prioridade", "aberto_em", "prazo_resposta", "prazo_solucao",
                       "primeira_resposta_em", "resolvido_em", "tempo_pausado", "criado_por")
    inlines = [ComentarioInline, AnexoInline, HistoricoInline]

    def has_delete_permission(self, request, obj=None):
        return False  # chamado nunca e apagado: e cancelado

    def get_readonly_fields(self, request, obj=None):
        # O cliente define o SLA: nao muda depois da abertura
        return self.readonly_fields + (("cliente",) if obj else ())

    def save_model(self, request, obj, form, change):
        # Passa pela camada de servicos (numero, SLA, historico)
        dados = {c: form.cleaned_data[c] for c in form.cleaned_data if hasattr(obj, c)}
        try:
            if change:
                novo = services.atualizar_chamado(Chamado.objects.get(pk=obj.pk), request.user, **dados)
            else:
                dados.pop("status", None)
                novo = services.abrir_chamado(request.user, **dados)
        except ValueError as e:
            messages.error(request, str(e))
            return
        obj.pk = novo.pk
        obj.refresh_from_db()
