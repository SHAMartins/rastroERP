"""Regra: OS nunca e apagada; e cancelada. A trilha de auditoria deve sobreviver."""
import pytest
from django.contrib.admin.sites import AdminSite
from django.db.models import ProtectedError
from django.test import RequestFactory
from rest_framework.test import APIClient

from . import services
from .admin import OrdemAdmin
from .models import OrdemServico

pytestmark = pytest.mark.django_db


def test_admin_nao_permite_apagar_os(usuario, ordem):
    request = RequestFactory().get("/admin/")
    request.user = usuario
    admin = OrdemAdmin(OrdemServico, AdminSite())
    assert admin.has_delete_permission(request) is False
    assert admin.has_delete_permission(request, ordem) is False


def test_banco_protege_os_com_historico(ordem):
    # abrir_os ja grava o historico de criacao; ele impede a exclusao
    with pytest.raises(ProtectedError):
        ordem.delete()
    assert OrdemServico.objects.filter(pk=ordem.pk).exists()


def test_banco_protege_os_com_comentario(usuario, ordem):
    services.comentar(ordem, usuario, "Visita agendada")
    with pytest.raises(ProtectedError):
        ordem.delete()


def test_api_nao_aceita_delete(usuario, ordem):
    client = APIClient()
    client.force_authenticate(usuario)
    resposta = client.delete(f"/api/ordens/{ordem.pk}/")
    assert resposta.status_code == 405
    assert OrdemServico.objects.filter(pk=ordem.pk).exists()


def test_cancelar_e_o_caminho_correto(usuario, ordem):
    services.atualizar_os(ordem, usuario, status=OrdemServico.Status.CANCELADA)
    ordem.refresh_from_db()
    assert ordem.status == OrdemServico.Status.CANCELADA
    assert ordem.historico.filter(campo="status", valor_novo="Cancelada").exists()
