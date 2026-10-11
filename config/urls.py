from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

admin.site.site_header = admin.site.site_title = "Rastro - Administracao"
admin.site.index_title = "Administracao do sistema"

# Uma unica porta de entrada (com limite de tentativas): o login do admin redireciona para /entrar/
urlpatterns = [
    path("admin/login/", RedirectView.as_view(url="/entrar/", query_string=True)),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("atividades/", include("chamados.urls")),   # chamado + OS na mesma tela
    path("ordens/", include("ordens.urls")),
    path("cadastros/", include("clientes.urls")),
    path("estoque/", include("estoque.urls")),
    path("", include("seguranca.urls")),
    path("", include("dashboard.urls")),
]
# /media/ nao e servido: anexos saem por /anexos/<origem>/<id>/, que exige login
handler403 = "seguranca.views.acesso_negado"
