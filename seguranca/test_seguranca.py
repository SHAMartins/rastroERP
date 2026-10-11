"""Seguranca: perfis (RBAC/IDOR), login com bloqueio, senhas, token, limites, anexos, cabecalhos e log."""
import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from chamados.models import AnexoChamado
from estoque.models import Produto

from .models import EventoSeguranca as E

pytestmark = pytest.mark.django_db
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def entrar(client, usuario):
    client.force_login(usuario)
    return client


# ---------------- Perfis (RBAC) e IDOR ----------------

def test_tecnico_nao_tria_nem_gera_os(client, com_perfil, chamado):
    entrar(client, com_perfil("Tecnico"))
    assert client.post(f"/atividades/{chamado.pk}/status/", {"status": "CANCELADO"}).status_code == 403
    assert client.post(f"/atividades/{chamado.pk}/gerar-os/", {"nova_os-titulo": "x"}).status_code == 403
    chamado.refresh_from_db()
    assert chamado.status == "NOVO" and not chamado.ordens.exists()


def test_tecnico_opera_so_a_propria_os(client, com_perfil, ordem):
    tecnico, outro = com_perfil("Tecnico"), com_perfil("Tecnico", "outro")
    ordem.responsavel = tecnico
    ordem.save()
    pre = f"os{ordem.pk}"
    entrar(client, outro)
    assert client.post(f"/ordens/{ordem.pk}/status/", {f"{pre}-status": "EM_ANDAMENTO"}).status_code == 403
    entrar(client, tecnico)
    assert client.post(f"/ordens/{ordem.pk}/status/", {f"{pre}-status": "EM_ANDAMENTO"}).status_code == 302
    ordem.refresh_from_db()
    assert ordem.status == "EM_ANDAMENTO"


def test_api_tambem_barra_os_de_outro_tecnico(com_perfil, ordem):
    api = APIClient()
    api.force_authenticate(com_perfil("Tecnico"))
    assert api.patch(f"/api/ordens/{ordem.pk}/", {"status": "FECHADA"}, format="json").status_code == 403
    assert api.patch(f"/api/chamados/{ordem.chamado_id}/", {"status": "CANCELADO"}, format="json").status_code == 403
    assert api.get(f"/api/ordens/{ordem.pk}/").status_code == 200          # consultar pode


def test_coordenacao_resolve_mas_nao_mexe_no_estoque(client, com_perfil, chamado):
    entrar(client, com_perfil("Coordenacao"))
    r = client.post(f"/atividades/{chamado.pk}/status/", {"status": "RESOLVIDO", "nota_resolucao": "ok",
                                                          "categoria_encerramento": "REMOTO"})
    assert r.status_code == 302
    produto = Produto.objects.create(codigo="P", nome="Cabo")
    assert client.post(f"/estoque/produtos/{produto.pk}/entrada/", {"entrada-quantidade": 5}).status_code == 403
    assert produto.saldo == 0


def test_estoque_lanca_entrada_mas_nao_edita_sla(client, com_perfil):
    entrar(client, com_perfil("Estoque"))
    produto = Produto.objects.create(codigo="P", nome="Cabo")
    client.post(f"/estoque/produtos/{produto.pk}/entrada/", {"entrada-quantidade": 5})
    assert produto.saldo == 5
    assert client.get("/cadastros/sla/").status_code == 403


def test_tela_e_menu_escondem_o_que_o_perfil_nao_pode(client, com_perfil, chamado):
    entrar(client, com_perfil("Tecnico"))
    html = client.get(f"/atividades/{chamado.pk}/").content.decode()
    assert 'id="form-status"' not in html and "Gerar OS" not in html
    assert "SLA padrao" not in html and "Usuarios" not in html          # itens do menu
    assert "Perfil: Tecnico" in html


def test_acesso_negado_fica_no_log(client, com_perfil):
    tecnico = com_perfil("Tecnico")
    entrar(client, tecnico)
    client.get("/seguranca/usuarios/")
    assert E.objects.filter(tipo=E.Tipo.ACESSO_NEGADO, usuario=tecnico, detalhe__contains="/seguranca/usuarios/").exists()


# ---------------- Login: bloqueio por tentativas e log ----------------

def test_bloqueia_depois_de_5_senhas_erradas_mesmo_com_a_senha_certa(client, com_perfil):
    com_perfil("Tecnico", "joao")
    for _ in range(5):
        client.post("/entrar/", {"username": "joao", "password": "errada"})
    r = client.post("/entrar/", {"username": "joao", "password": "Senha-forte-123"})
    assert "Muitas tentativas" in r.content.decode() and "_auth_user_id" not in client.session
    assert E.objects.filter(tipo=E.Tipo.LOGIN_FALHA, nome_usuario="joao").count() == 5
    assert E.objects.filter(tipo=E.Tipo.BLOQUEIO, nome_usuario="joao").exists()


def test_login_certo_entra_registra_e_nao_guarda_senha(client, com_perfil):
    com_perfil("Tecnico", "maria")
    client.post("/entrar/", {"username": "maria", "password": "errada"})
    r = client.post("/entrar/", {"username": "maria", "password": "Senha-forte-123"})
    assert r.status_code == 302 and "_auth_user_id" in client.session
    assert E.objects.filter(tipo=E.Tipo.LOGIN_OK, nome_usuario="maria").exists()
    assert not E.objects.filter(detalhe__icontains="Senha-forte").exists()
    assert not E.objects.filter(detalhe__icontains="errada").exists()


def test_mensagem_de_erro_nao_revela_se_usuario_existe(client, com_perfil):
    com_perfil("Tecnico", "ana")
    existe = client.post("/entrar/", {"username": "ana", "password": "x"}).content.decode()
    nao_existe = client.post("/entrar/", {"username": "fantasma", "password": "x"}).content.decode()
    assert "Usuario ou senha incorretos" in existe and "Usuario ou senha incorretos" in nao_existe


def test_login_do_admin_passa_pela_mesma_porta(client):
    r = client.get("/admin/login/?next=/admin/")
    assert r.status_code == 302 and r.url.startswith("/entrar/")


# ---------------- Senhas ----------------

def test_senha_fraca_e_recusada_e_forte_usa_argon2(client, usuario):
    entrar(client, usuario)
    base = {"username": "novo", "perfil": "Tecnico", "is_active": "on"}
    r = client.post("/seguranca/usuarios/novo/", {**base, "senha": "123456", "senha2": "123456"})
    assert "senha" in r.context["form"].errors and not get_user_model().objects.filter(username="novo").exists()
    client.post("/seguranca/usuarios/novo/", {**base, "senha": "Fibra-Optica-2026", "senha2": "Fibra-Optica-2026"})
    novo = get_user_model().objects.get(username="novo")
    assert novo.password.startswith("argon2") and novo.groups.get().name == "Tecnico" and not novo.is_staff
    assert E.objects.filter(tipo=E.Tipo.USUARIO_CRIADO, usuario=novo, autor=usuario).exists()


def test_mudanca_de_perfil_fica_no_log_com_o_autor(client, usuario, com_perfil):
    tecnico = com_perfil("Tecnico")
    entrar(client, usuario)
    client.post(f"/seguranca/usuarios/{tecnico.pk}/", {"username": tecnico.username, "perfil": "Coordenacao",
                                                        "is_active": "on"})
    evento = E.objects.filter(tipo=E.Tipo.PERFIL_ALTERADO, usuario=tecnico).latest("criado_em")
    assert "Coordenacao" in evento.detalhe and evento.autor == usuario


def test_administrador_nao_se_tranca_para_fora(client, com_perfil):
    admin = com_perfil("Administrador")
    entrar(client, admin)
    r = client.post(f"/seguranca/usuarios/{admin.pk}/", {"username": admin.username, "perfil": "Tecnico"})
    erros = r.context["form"].errors
    assert "perfil" in erros and "is_active" in erros


def test_log_de_seguranca_e_imutavel():
    evento = E.objects.create(tipo=E.Tipo.LOGIN_OK, nome_usuario="x")
    with pytest.raises(Exception):
        evento.save()
    with pytest.raises(Exception):
        evento.delete()


# ---------------- API: token com validade e limite de requisicoes ----------------

def test_token_tem_validade_e_e_rotacionado(com_perfil):
    com_perfil("Tecnico", "api")
    api = APIClient()
    r1 = api.post("/api/token/", {"username": "api", "password": "Senha-forte-123"})
    assert r1.status_code == 200 and "expira_em" in r1.data
    r2 = api.post("/api/token/", {"username": "api", "password": "Senha-forte-123"})
    assert r2.data["token"] != r1.data["token"]
    api.credentials(HTTP_AUTHORIZATION=f"Token {r1.data['token']}")
    assert api.get("/api/chamados/").status_code == 401                 # o antigo foi invalidado
    api.credentials(HTTP_AUTHORIZATION=f"Token {r2.data['token']}")
    assert api.get("/api/chamados/").status_code == 200
    Token.objects.filter(key=r2.data["token"]).update(created=timezone.now() - timedelta(hours=9))
    r = api.get("/api/chamados/")
    assert r.status_code == 401 and "expirado" in str(r.data)


def test_emissao_de_token_tem_limite_por_minuto():
    api = APIClient()
    codigos = [api.post("/api/token/", {"username": "x", "password": "y"}).status_code for _ in range(11)]
    assert codigos[:10] == [400] * 10 and codigos[10] == 429


def test_api_exige_login():
    assert APIClient().get("/api/chamados/").status_code == 401


# ---------------- Anexos ----------------

@pytest.mark.parametrize("nome,conteudo,erro", [
    ("pagina.html", b"<script>alert(1)</script>", "nao permitido"),
    ("imagem.svg", b"<svg onload=alert(1)>", "nao permitido"),
    ("laudo.pdf", b"<script>nao sou pdf</script>", "nao corresponde"),
])
def test_anexo_perigoso_ou_falso_e_recusado(client, usuario, chamado, nome, conteudo, erro):
    entrar(client, usuario)
    r = client.post(f"/atividades/{chamado.pk}/anexar/", {"anexo-arquivo": SimpleUploadedFile(nome, conteudo)},
                    follow=True)
    assert erro in r.content.decode() and not AnexoChamado.objects.exists()


@override_settings(ANEXO_TAMANHO_MAX_MB=0)
def test_anexo_grande_demais_e_recusado(client, usuario, chamado):
    entrar(client, usuario)
    client.post(f"/atividades/{chamado.pk}/anexar/", {"anexo-arquivo": SimpleUploadedFile("foto.png", PNG)})
    assert not AnexoChamado.objects.exists()


def test_anexo_so_baixa_com_login_e_com_cabecalhos_seguros(client, usuario, chamado, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    entrar(client, usuario)
    client.post(f"/atividades/{chamado.pk}/anexar/", {"anexo-arquivo": SimpleUploadedFile("foto.png", PNG)})
    anexo = AnexoChamado.objects.get()
    r = client.get(anexo.url_download)
    assert r.status_code == 200 and r["X-Content-Type-Options"] == "nosniff" and "sandbox" in r["Content-Security-Policy"]
    client.logout()
    assert client.get(anexo.url_download).status_code == 302                  # sem login: vai para /entrar/
    assert client.get(f"/media/{anexo.arquivo.name}").status_code == 404      # /media/ nao e publico


# ---------------- Cabecalhos de seguranca ----------------

def test_csp_com_nonce_e_sem_scripts_inline_soltos(client, usuario, chamado):
    entrar(client, usuario)
    r = client.get(f"/atividades/{chamado.pk}/")
    csp = r["Content-Security-Policy"]
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    html = r.content.decode()
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    scripts_inline = re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*application/json)([^>]*)>", html)
    assert scripts_inline and all(f'nonce="{nonce}"' in attrs for attrs in scripts_inline)
    assert not re.search(r"\son(click|change|load|submit)=", html)
    assert r["X-Content-Type-Options"] == "nosniff" and r["X-Frame-Options"] == "DENY"
    assert "camera=(self)" in r["Permissions-Policy"]


def test_nonce_muda_a_cada_resposta(client, usuario):
    entrar(client, usuario)
    assert client.get("/")["Content-Security-Policy"] != client.get("/")["Content-Security-Policy"]


def test_sem_login_vai_para_a_tela_de_entrar_e_nao_para_acesso_negado(client):
    for url in ["/atividades/novo/", "/seguranca/usuarios/", "/seguranca/eventos/", "/cadastros/sla/", "/"]:
        r = client.get(url)
        assert r.status_code == 302 and r.url.startswith("/entrar/"), url


def test_swagger_usa_politica_relaxada_sem_nonce(client, usuario):
    entrar(client, usuario)
    csp = client.get("/api/docs/")["Content-Security-Policy"]
    script_src = csp.split("script-src")[1].split(";")[0]
    assert "'unsafe-inline'" in script_src and "nonce-" not in script_src   # com nonce o unsafe-inline seria ignorado
