from django.urls import path

from . import views

urlpatterns = [
    path("", views.geral, name="dashboard"),
    path("paineis/triagem/", views.triagem, name="painel_triagem"),
    path("paineis/manutencao/", views.manutencao, name="painel_manutencao"),
    path("paineis/instalacao/", views.instalacao, name="painel_instalacao"),
]
