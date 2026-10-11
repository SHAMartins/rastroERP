"""Fixtures compartilhadas pelos testes de todos os apps."""
import pytest
from django.contrib.auth import get_user_model

from chamados import services as chamados
from clientes.models import Cliente


@pytest.fixture(autouse=True)
def cache_limpo():
    """Contadores de tentativas de login e limites da API ficam no cache: zera entre os testes."""
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def com_perfil(db):
    """Cria um usuario com um dos perfis (Administrador, Coordenacao, Tecnico, Estoque)."""
    from django.contrib.auth.models import Group

    def criar(perfil, nome=None):
        u = get_user_model().objects.create_user(nome or f"u_{perfil.lower()}", password="Senha-forte-123")
        u.groups.add(Group.objects.get(name=perfil))
        return u
    return criar


@pytest.fixture
def usuario(db):
    return get_user_model().objects.create_superuser("tecnico", "tecnico@teste.com", "senha-teste")


@pytest.fixture
def logado(client, usuario):
    client.force_login(usuario)
    return client


@pytest.fixture
def cliente(db):
    return Cliente.objects.create(nome="Operadora Sul", documento="11.111.111/0001-11")


@pytest.fixture
def chamado(usuario, cliente):
    return chamados.abrir_chamado(
        usuario, tipo="MANUTENCAO", cliente=cliente, titulo="Link sem sinal", solicitante_nome="Ana",
        cliente_final="Mercado Bom Preco - Loja 3", endereco="Rua B, 2", ativo="CIRC-0001",
        impacto="ALTO", urgencia="ALTA",
        detalhes={"sintoma": "ONT com LOS vermelho", "desde_quando": "2026-10-11T08:00", "afetados": "UNIDADE"})


@pytest.fixture
def ordem(usuario, chamado):
    return chamados.gerar_os(chamado, usuario, titulo="Verificar ONT")
