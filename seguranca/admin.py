from django.contrib import admin

from .models import EventoSeguranca


@admin.register(EventoSeguranca)
class EventoSegurancaAdmin(admin.ModelAdmin):
    """Somente leitura: o log de seguranca nao e criado, editado nem apagado a mao."""
    list_display = ("criado_em", "tipo", "nome_usuario", "ip", "autor", "detalhe")
    list_filter = ("tipo",)
    search_fields = ("nome_usuario", "ip", "detalhe")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
