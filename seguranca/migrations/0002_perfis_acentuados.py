"""Renomeia os perfis Coordenacao -> Coordenação e Tecnico -> Técnico, mantendo os usuários de cada um.

Roda antes do post_migrate (sincronizar_perfis); assim a sincronização encontra os grupos já com o nome novo
e não cria grupos duplicados.
"""
from django.db import migrations

NOMES = {"Coordenacao": "Coordenação", "Tecnico": "Técnico"}


def _renomear(apps, de_para):
    Group = apps.get_model("auth", "Group")
    for antigo, novo in de_para.items():
        grupo_antigo = Group.objects.filter(name=antigo).first()
        if grupo_antigo is None:
            continue
        grupo_novo = Group.objects.filter(name=novo).first()
        if grupo_novo is None:
            grupo_antigo.name = novo
            grupo_antigo.save(update_fields=["name"])
        else:                                   # os dois já existem: junta os usuários no grupo novo
            grupo_novo.user_set.add(*grupo_antigo.user_set.all())
            grupo_antigo.delete()


def acentuar(apps, schema_editor):
    _renomear(apps, NOMES)


def desfazer(apps, schema_editor):
    _renomear(apps, {novo: antigo for antigo, novo in NOMES.items()})


class Migration(migrations.Migration):
    dependencies = [
        ("seguranca", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(acentuar, desfazer)]
