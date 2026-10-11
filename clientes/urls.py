from django.urls import path

from . import views

app_name = "cadastros"
urlpatterns = [
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/novo/", views.cliente_form, name="cliente_novo"),
    path("clientes/<int:pk>/", views.cliente_form, name="cliente"),
    path("clientes/<int:pk>/sla/", views.sla, name="sla_cliente"),
    path("sla/", views.sla, name="sla_padrao"),
    path("servicos/", views.servicos, name="servicos"),
    path("servicos/<int:pk>/", views.servicos, name="servico"),
]
