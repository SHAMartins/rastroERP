"""SLA padrao (vale para clientes sem contrato proprio). Valores de partida: ajuste em Cadastros > SLA."""
from django.db import migrations

# (horas de primeira resposta, horas de solucao) por tipo e prioridade
SLA_PADRAO = {
    "INCIDENTE": {"URGENTE": (0.5, 4), "ALTA": (1, 8), "MEDIA": (4, 24), "BAIXA": (8, 48)},
    "CORRETIVA": {"URGENTE": (2, 8), "ALTA": (4, 24), "MEDIA": (8, 48), "BAIXA": (24, 72)},
    "PREVENTIVA": {"URGENTE": (8, 48), "ALTA": (24, 72), "MEDIA": (24, 120), "BAIXA": (48, 240)},
    "INSTALACAO": {"URGENTE": (4, 72), "ALTA": (8, 120), "MEDIA": (24, 240), "BAIXA": (24, 360)},
    "EXECUCAO": {"URGENTE": (4, 24), "ALTA": (8, 48), "MEDIA": (24, 72), "BAIXA": (48, 120)},
}


def criar(apps, schema_editor):
    PoliticaSLA = apps.get_model("chamados", "PoliticaSLA")
    for tipo, prioridades in SLA_PADRAO.items():
        for prioridade, (resposta, solucao) in prioridades.items():
            PoliticaSLA.objects.get_or_create(cliente=None, tipo=tipo, prioridade=prioridade,
                                              defaults={"horas_resposta": resposta, "horas_solucao": solucao})


def remover(apps, schema_editor):
    apps.get_model("chamados", "PoliticaSLA").objects.filter(cliente=None).delete()


class Migration(migrations.Migration):
    dependencies = [("chamados", "0001_initial")]
    operations = [migrations.RunPython(criar, remover)]
