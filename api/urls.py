from django.urls import include, path
from rest_framework.routers import DefaultRouter

from seguranca.api import ObterToken

from . import views

router = DefaultRouter()
router.register("clientes", views.ClienteViewSet)
router.register("chamados", views.ChamadoViewSet)
router.register("sla", views.PoliticaSLAViewSet)
router.register("servicos", views.ServicoViewSet)
router.register("produtos", views.ProdutoViewSet)
router.register("movimentacoes", views.MovimentacaoViewSet)
router.register("itens-serie", views.ItemSerieViewSet, basename="itemserie")
router.register("ordens", views.OrdemViewSet)

urlpatterns = [
    path("token/", ObterToken.as_view(), name="token"),   # token com validade + limite de tentativas
    path("", include(router.urls)),
]
