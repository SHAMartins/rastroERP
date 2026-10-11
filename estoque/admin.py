from django.contrib import admin
from .models import ItemSerie, MovimentacaoEstoque, Produto


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "tipo", "modelo", "cliente", "saldo", "estoque_minimo", "controla_serie", "ativo")
    list_filter = ("tipo", "controla_serie", "cliente", "ativo")
    search_fields = ("nome", "codigo", "modelo")

    def get_readonly_fields(self, request, obj=None):
        # Trocar o controle de serie com saldo quebraria a conferencia saldo x unidades
        return ("controla_serie",) if obj and obj.saldo else ()


@admin.register(ItemSerie)
class ItemSerieAdmin(admin.ModelAdmin):
    """Somente leitura: unidades nascem na entrada e mudam na baixa por OS ou ajuste."""
    list_display = ("numero_serie", "produto", "status", "saida")
    list_filter = ("status", "produto")
    search_fields = ("numero_serie",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MovimentacaoEstoque)
class MovimentacaoAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "produto", "tipo", "quantidade", "ordem", "usuario")
    list_filter = ("tipo",)

    def has_add_permission(self, request):
        # Movimentacoes so nascem pelas regras (entrada, ajuste com justificativa, baixa por OS)
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
