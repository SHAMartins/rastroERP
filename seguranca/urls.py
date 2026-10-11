from django.contrib.auth import views as auth
from django.urls import path

from . import views

app_name = "seguranca"
urlpatterns = [
    path("entrar/", views.Entrar.as_view(), name="entrar"),
    path("sair/", auth.LogoutView.as_view(), name="sair"),
    path("conta/senha/", views.TrocarSenha.as_view(), name="senha"),
    path("anexos/<str:origem>/<int:pk>/", views.baixar_anexo, name="anexo"),
    path("seguranca/usuarios/", views.usuarios, name="usuarios"),
    path("seguranca/usuarios/novo/", views.usuario_form, name="usuario_novo"),
    path("seguranca/usuarios/<int:pk>/", views.usuario_form, name="usuario"),
    path("seguranca/eventos/", views.eventos, name="eventos"),
]
