"""Perfis de acesso (RBAC). Cada perfil e um Group do Django com as permissoes abaixo.

A matriz fica so aqui. Ela e aplicada aos grupos a cada `migrate` (sinal post_migrate):
para mudar o que um perfil pode fazer, edite esta lista e rode `python manage.py migrate`.
"""
ADMINISTRADOR = "Administrador"
COORDENACAO = "Coordenação"
TECNICO = "Técnico"
ESTOQUE = "Estoque"

# Todos os perfis podem consultar tudo, abrir atividades, comentar e anexar
COMUM = ["chamados.add_chamado"]

PERFIS = {
    # None = todas as permissoes dos apps do sistema, inclusive usuarios e log de seguranca
    ADMINISTRADOR: None,
    COORDENACAO: COMUM + [
        "chamados.triar_chamado", "chamados.gerar_os", "chamados.gerenciar_sla", "ordens.operar_qualquer_os",
        "clientes.add_cliente", "clientes.change_cliente", "clientes.add_servico", "clientes.change_servico",
    ],
    # O tecnico opera so as OSs atribuidas a ele (regra em seguranca.permissoes.pode_operar_os)
    TECNICO: COMUM,
    ESTOQUE: COMUM + ["estoque.add_produto", "estoque.change_produto", "estoque.movimentar_estoque"],
}

DESCRICOES = {
    ADMINISTRADOR: "Tudo, inclusive usuários e log de segurança",
    COORDENACAO: "Triagem, gerar OS, resolver, cadastros e SLA; opera qualquer OS",
    TECNICO: "Opera as OSs atribuídas a ele (status, material); abre atividades",
    ESTOQUE: "Produtos, entradas e ajustes de estoque",
}

APPS_DO_SISTEMA = ["chamados", "ordens", "estoque", "clientes", "seguranca", "auth"]


def sincronizar_perfis(**kwargs):
    """Cria/atualiza os grupos com as permissoes da matriz. Idempotente."""
    from django.contrib.auth.models import Group, Permission

    for nome, permissoes in PERFIS.items():
        grupo, _ = Group.objects.get_or_create(name=nome)
        if permissoes is None:
            grupo.permissions.set(Permission.objects.filter(content_type__app_label__in=APPS_DO_SISTEMA))
            continue
        encontradas = []
        for p in permissoes:
            app, codigo = p.split(".")
            encontradas += list(Permission.objects.filter(content_type__app_label=app, codename=codigo))
        grupo.permissions.set(encontradas)
    _atualizar_nomes_das_permissoes()


def _atualizar_nomes_das_permissoes():
    """O Django cria as permissoes do Meta.permissions mas nunca renomeia: mantem o texto igual ao do model."""
    from django.apps import apps
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    for app in APPS_DO_SISTEMA:
        for model in apps.get_app_config(app).get_models():
            if not model._meta.permissions:
                continue
            tipo = ContentType.objects.get_for_model(model)
            for codigo, nome in model._meta.permissions:
                Permission.objects.filter(content_type=tipo, codename=codigo).exclude(name=nome).update(name=nome)


def perfil_de(usuario):
    if usuario.is_superuser:
        return ADMINISTRADOR
    nomes = set(usuario.groups.values_list("name", flat=True))
    return next((p for p in PERFIS if p in nomes), "")
