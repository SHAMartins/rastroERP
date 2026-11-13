from django.urls import path

from . import views

app_name = "estoque"
urlpatterns = [
    path("", views.produtos, name="produtos"),
    path("produtos/novo/", views.produto_form, name="produto_novo"),
    path("produtos/<int:pk>/", views.produto_form, name="produto"),
    path("produtos/<int:pk>/entrada/", views.entrada, name="entrada"),
    path("produtos/<int:pk>/ajuste/", views.ajuste, name="ajuste"),
    path("movimentacoes/", views.movimentacoes, name="movimentacoes"),
    path("movimentacoes/exportar/", views.exportar_movimentacoes, name="exportar_movimentacoes"),
    path("reposicao/", views.reposicoes, name="reposicoes"),
    path("reposicao/<int:pk>/assumir/", views.assumir_reposicao, name="assumir_reposicao"),
    path("reposicao/<int:pk>/cancelar/", views.cancelar_reposicao, name="cancelar_reposicao"),
]
