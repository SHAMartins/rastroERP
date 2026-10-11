from django.urls import path

from . import views

app_name = "ordens"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/status/", views.alterar_status, name="status"),
    path("<int:pk>/material/", views.usar_material, name="material"),
]
