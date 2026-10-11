from django.contrib import admin

from estoque.models import MovimentacaoEstoque

from chamados import services as chamados

from . import services
from .models import Anexo, Comentario, HistoricoAlteracao, OrdemServico


class AnexoInline(admin.TabularInline):
    model = Anexo
    extra = 0
    can_delete = False
    readonly_fields = ("enviado_por", "enviado_em")


class ComentarioInline(admin.TabularInline):
    model = Comentario
    extra = 1
    fields = ("texto", "autor", "criado_em")
    readonly_fields = ("autor", "criado_em")
    can_delete = False

    def has_change_permission(self, request, obj=None):
        return False


class MaterialInline(admin.TabularInline):
    model = MovimentacaoEstoque
    fk_name = "ordem"
    verbose_name_plural = "materiais utilizados"
    extra = 0
    fields = ("criado_em", "produto", "quantidade", "usuario")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class HistoricoInline(admin.TabularInline):
    model = HistoricoAlteracao
    extra = 0
    fields = ("alterado_em", "usuario", "campo", "valor_anterior", "valor_novo")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrdemServico)
class OrdemAdmin(admin.ModelAdmin):
    list_display = ("numero", "chamado", "titulo", "cliente", "prioridade", "status", "responsavel", "data_abertura")
    list_filter = ("status", "prioridade", "cliente", "responsavel")
    search_fields = ("numero", "titulo", "chamado__numero", "chamado__cliente_final")
    readonly_fields = ("numero", "cliente", "data_abertura", "data_fechamento", "criado_por", "endereco", "coordenadas")
    autocomplete_fields = ("chamado",)
    inlines = [ComentarioInline, AnexoInline, MaterialInline, HistoricoInline]

    def has_delete_permission(self, request, obj=None):
        # OS nunca e apagada: e cancelada (preserva a trilha de auditoria)
        return False

    def get_readonly_fields(self, request, obj=None):
        # O chamado de origem nao muda depois que a OS existe
        return self.readonly_fields + (("chamado",) if obj else ())

    def save_model(self, request, obj, form, change):
        # Passa pela camada de servicos para gerar numero e historico
        dados = {c: form.cleaned_data[c] for c in form.cleaned_data if hasattr(obj, c)}
        if change:
            original = OrdemServico.objects.get(pk=obj.pk)
            novo = services.atualizar_os(original, request.user, **dados)
        else:
            novo = chamados.gerar_os(dados.pop("chamado"), request.user, **dados)
        obj.pk, obj.numero = novo.pk, novo.numero
        obj.refresh_from_db()

    def save_formset(self, request, form, formset, change):
        for inst in formset.save(commit=False):
            if isinstance(inst, Comentario):
                inst.autor = request.user
            if isinstance(inst, Anexo):
                inst.enviado_por = request.user
            inst.save()
        formset.save_m2m()
