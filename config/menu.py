"""Menu lateral do sistema. Cada modulo tem um icone (Bootstrap Icons) e seus subitens.

Modulo sem "itens" e um link direto; com "itens" abre o painel lateral (flyout).
Item com "perm" so aparece para quem tem a permissao ("staff" = acesso ao admin do Django).
Esconder o item e so conforto visual: cada tela confere a permissao de novo no back-end.
"""

MENU = [
    {"nome": "Paineis", "icone": "bi-grid-1x2", "prefixos": ["/$", "/paineis/"], "itens": [
        {"nome": "Geral", "url": "/", "icone": "bi-speedometer2"},
        {"nome": "Triagem", "url": "/paineis/triagem/", "icone": "bi-inbox"},
        {"nome": "Manutencao", "url": "/paineis/manutencao/", "icone": "bi-wrench-adjustable"},
        {"nome": "Instalacao", "url": "/paineis/instalacao/", "icone": "bi-router"},
    ]},
    # Atividade = chamado + suas OSs, na mesma tela
    {"nome": "Atividades", "icone": "bi-headset", "prefixos": ["/atividades/", "/ordens/"], "itens": [
        {"nome": "Nova atividade", "url": "/atividades/novo/", "icone": "bi-plus-circle", "perm": "chamados.add_chamado"},
        {"nome": "Fila em aberto", "url": "/atividades/", "icone": "bi-list-ol"},
        {"nome": "Aguardando triagem", "url": "/atividades/?status=NOVO", "icone": "bi-inbox"},
        {"nome": "Manutencao", "url": "/atividades/?tipo=MANUTENCAO", "icone": "bi-wrench-adjustable"},
        {"nome": "Instalacao", "url": "/atividades/?tipo=INSTALACAO", "icone": "bi-router"},
        {"nome": "Minhas OSs", "url": "/atividades/?minhas=1", "icone": "bi-person-check"},
        {"nome": "Todas", "url": "/atividades/?visao=todos", "icone": "bi-archive"},
    ]},
    {"nome": "Estoque", "icone": "bi-box-seam", "prefixos": ["/estoque/"], "itens": [
        {"nome": "Produtos", "url": "/estoque/", "icone": "bi-boxes"},
        {"nome": "Novo produto", "url": "/estoque/produtos/novo/", "icone": "bi-plus-circle", "perm": "estoque.add_produto"},
        {"nome": "Estoque baixo", "url": "/estoque/?filtro=baixo", "icone": "bi-exclamation-triangle"},
        {"nome": "Movimentacoes", "url": "/estoque/movimentacoes/", "icone": "bi-arrow-left-right"},
    ]},
    {"nome": "Cadastros", "icone": "bi-person-vcard", "prefixos": ["/cadastros/"], "itens": [
        {"nome": "Clientes", "url": "/cadastros/clientes/", "icone": "bi-people"},
        {"nome": "Novo cliente", "url": "/cadastros/clientes/novo/", "icone": "bi-person-plus", "perm": "clientes.add_cliente"},
        {"nome": "Servicos", "url": "/cadastros/servicos/", "icone": "bi-card-checklist"},
        {"nome": "SLA padrao", "url": "/cadastros/sla/", "icone": "bi-stopwatch", "perm": "chamados.gerenciar_sla"},
    ]},
    {"nome": "Seguranca", "icone": "bi-shield-lock", "prefixos": ["/seguranca/"], "itens": [
        {"nome": "Usuarios", "url": "/seguranca/usuarios/", "icone": "bi-people", "perm": "auth.change_user"},
        {"nome": "Log de seguranca", "url": "/seguranca/eventos/", "icone": "bi-journal-lock",
         "perm": "seguranca.view_eventoseguranca"},
        {"nome": "Administracao (Django)", "url": "/admin/", "icone": "bi-gear", "perm": "staff"},
    ]},
    {"nome": "API", "icone": "bi-braces", "url": "/api/docs/", "prefixos": ["/api/"]},
]


def _ativo(caminho, prefixos):
    return any(caminho == "/" if p == "/$" else caminho.startswith(p) for p in prefixos)


def _pode(usuario, item):
    perm = item.get("perm")
    if not perm:
        return True
    return usuario.is_staff if perm == "staff" else usuario.has_perm(perm)


def menu(request):
    """Context processor: menu filtrado pelo perfil, com o modulo atual marcado."""
    usuario = getattr(request, "user", None)
    if not usuario or not usuario.is_authenticated:
        return {"menu": []}
    from seguranca.perfis import perfil_de
    modulos = []
    for m in MENU:
        itens = [i for i in m.get("itens", []) if _pode(usuario, i)]
        if "itens" in m and not itens:
            continue
        modulos.append(dict(m, itens=itens, ativo=_ativo(request.path, m["prefixos"])))
    return {"menu": modulos, "perfil_usuario": perfil_de(usuario)}
