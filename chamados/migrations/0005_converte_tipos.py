"""Converte os 5 tipos antigos para Manutencao/Instalacao e refaz o SLA padrao.

Incidente, corretiva e preventiva -> Manutencao; execucao de servico -> Instalacao.
"""
from django.db import migrations

DE_PARA = {"INCIDENTE": "MANUTENCAO", "CORRETIVA": "MANUTENCAO", "PREVENTIVA": "MANUTENCAO",
           "EXECUCAO": "INSTALACAO"}
# (horas de primeira resposta, horas de solucao). Valores de partida: ajuste em Cadastros > SLA.
SLA_PADRAO = {
    "MANUTENCAO": {"URGENTE": (0.5, 4), "ALTA": (1, 8), "MEDIA": (4, 24), "BAIXA": (8, 72)},
    "INSTALACAO": {"URGENTE": (4, 48), "ALTA": (8, 120), "MEDIA": (24, 240), "BAIXA": (24, 360)},
}


def converter(apps, schema_editor):
    Chamado = apps.get_model("chamados", "Chamado")
    PoliticaSLA = apps.get_model("chamados", "PoliticaSLA")
    for antigo, novo in DE_PARA.items():
        Chamado.objects.filter(tipo=antigo).update(tipo=novo)

    # Contratos de clientes: o primeiro prazo de cada (cliente, tipo novo, prioridade) vale; o resto e duplicado
    vistos = set()
    for p in PoliticaSLA.objects.filter(cliente__isnull=False).order_by("cliente_id", "tipo", "prioridade"):
        chave = (p.cliente_id, DE_PARA.get(p.tipo, p.tipo), p.prioridade)
        if chave in vistos:
            p.delete()
            continue
        vistos.add(chave)
        PoliticaSLA.objects.filter(pk=p.pk).update(tipo=chave[1])

    PoliticaSLA.objects.filter(cliente__isnull=True).delete()
    for tipo, prioridades in SLA_PADRAO.items():
        for prioridade, (resposta, solucao) in prioridades.items():
            PoliticaSLA.objects.create(cliente=None, tipo=tipo, prioridade=prioridade,
                                       horas_resposta=resposta, horas_solucao=solucao)


class Migration(migrations.Migration):
    dependencies = [("chamados", "0004_tipos_manutencao_instalacao")]
    operations = [migrations.RunPython(converter, migrations.RunPython.noop)]
