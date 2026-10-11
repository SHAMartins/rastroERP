from django.urls import path

from . import views

app_name = "chamados"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.novo, name="novo"),
    path("previa-sla/", views.previa_sla, name="previa_sla"),
    path("campos-tipo/", views.campos_tipo, name="campos_tipo"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/comentar/", views.comentar, name="comentar"),
    path("<int:pk>/status/", views.alterar_status, name="status"),
    path("<int:pk>/gerar-os/", views.gerar_os, name="gerar_os"),
    path("<int:pk>/anexar/", views.anexar, name="anexar"),
]
