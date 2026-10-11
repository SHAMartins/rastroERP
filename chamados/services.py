"""Regras de negocio dos chamados. Usadas pelas telas, pelo admin e pela API."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ordens import services as ordens
from ordens.services import valor_auditado

from seguranca.arquivos import validar_anexo

from .campos import campos_do_tipo, formatar, validar_detalhes
from .models import AnexoChamado, Chamado, ComentarioChamado, HistoricoChamado, PoliticaSLA, Prioridade, Tipo

# Matriz de prioridade (ITIL): prioridade = impacto x urgencia
MATRIZ_PRIORIDADE = {
    ("ALTO", "ALTA"): Prioridade.URGENTE, ("ALTO", "MEDIA"): Prioridade.ALTA, ("ALTO", "BAIXA"): Prioridade.MEDIA,
    ("MEDIO", "ALTA"): Prioridade.ALTA, ("MEDIO", "MEDIA"): Prioridade.MEDIA, ("MEDIO", "BAIXA"): Prioridade.BAIXA,
    ("BAIXO", "ALTA"): Prioridade.MEDIA, ("BAIXO", "MEDIA"): Prioridade.BAIXA, ("BAIXO", "BAIXA"): Prioridade.BAIXA,
}
TIPOS_COM_ATIVO = ("MANUTENCAO",)


def calcular_prioridade(impacto, urgencia):
    return MATRIZ_PRIORIDADE[(impacto, urgencia)]


def politica_sla(cliente, tipo, prioridade):
    """Contrato do cliente tem preferencia; sem contrato vale o padrao geral; sem nenhum, nao ha SLA."""
    politicas = PoliticaSLA.objects.filter(tipo=tipo, prioridade=prioridade)
    return (politicas.filter(cliente=cliente).first() if cliente else None) \
        or politicas.filter(cliente__isnull=True).first()


def _aplicar_sla(chamado):
    """(Re)calcula prioridade e prazos a partir da abertura."""
    chamado.prioridade = calcular_prioridade(chamado.impacto, chamado.urgencia)
    politica = politica_sla(chamado.cliente, chamado.tipo, chamado.prioridade)
    if politica:
        chamado.prazo_resposta = chamado.aberto_em + timedelta(hours=float(politica.horas_resposta))
        chamado.prazo_solucao = chamado.aberto_em + timedelta(hours=float(politica.horas_solucao))
    else:
        chamado.prazo_resposta = chamado.prazo_solucao = None


def _gerar_numero():
    ano = timezone.now().year
    prefixo = f"CH-{ano}-"
    ultimo = (Chamado.objects.select_for_update()
              .filter(numero__startswith=prefixo).order_by("-numero").first())
    seq = int(ultimo.numero.rsplit("-", 1)[1]) + 1 if ultimo else 1
    return f"{prefixo}{seq:05d}"          # ex.: CH-2026-00001


def _validar(chamado):
    if chamado.tipo in TIPOS_COM_ATIVO and not chamado.ativo.strip():
        raise ValueError("Informe o ativo ou circuito (obrigatorio para manutencao).")
    chamado.detalhes = validar_detalhes(chamado.tipo, chamado.detalhes or {})


def _historico_detalhes(chamado, usuario, antes):
    """Uma linha de historico por campo especifico alterado (campo gravado como 'detalhe.<nome>')."""
    campos = {c.nome: c for c in campos_do_tipo(chamado.tipo)}
    for nome in sorted(set(antes) | set(chamado.detalhes)):
        velho, novo = antes.get(nome, ""), chamado.detalhes.get(nome, "")
        if velho != novo:
            c = campos.get(nome)
            _historico(chamado, usuario, f"detalhe.{nome}", formatar(c, novo) if c and novo else novo,
                       formatar(c, velho) if c and velho else velho)


def _marcar_primeira_resposta(chamado, agora):
    if not chamado.primeira_resposta_em:
        chamado.primeira_resposta_em = agora


def _historico(chamado, usuario, campo, novo, anterior=""):
    HistoricoChamado.objects.create(chamado=chamado, usuario=usuario, campo=campo,
                                    valor_anterior=anterior, valor_novo=novo)


def _resumo_sla(chamado):
    if not chamado.prazo_solucao:
        return "sem SLA definido"
    return (f"resposta ate {timezone.localtime(chamado.prazo_resposta):%d/%m %H:%M}, "
            f"solucao ate {timezone.localtime(chamado.prazo_solucao):%d/%m %H:%M}")


@transaction.atomic
def abrir_chamado(usuario, **dados):
    chamado = Chamado(numero=_gerar_numero(), criado_por=usuario, aberto_em=timezone.now(), **dados)
    _validar(chamado)
    _aplicar_sla(chamado)
    chamado.save()
    _historico(chamado, usuario, "criacao",
               f"Chamado aberto com prioridade {chamado.get_prioridade_display()}; SLA: {_resumo_sla(chamado)}")
    return chamado


@transaction.atomic
def atualizar_chamado(chamado, usuario, **dados):
    """Aplica alteracoes, controla o relogio do SLA e registra uma linha de historico por campo."""
    chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
    status_antes = chamado.status
    status_novo = dados.get("status", status_antes)
    if chamado.encerrado and status_novo == status_antes:
        raise ValueError("Chamado resolvido/cancelado nao pode ser editado. Reabra antes.")

    antes = {c: valor_auditado(chamado, c) for c in Chamado.CAMPOS_AUDITADOS}
    detalhes_antes = dict(chamado.detalhes)
    for campo, valor in dados.items():
        if (campo in Chamado.CAMPOS_AUDITADOS and campo != "prioridade") or campo == "detalhes":
            setattr(chamado, campo, valor)
    _validar(chamado)

    # Reclassificacao (tipo, impacto ou urgencia) recalcula prioridade e prazos
    if any(valor_auditado(chamado, c) != antes[c] for c in ("tipo", "impacto", "urgencia")):
        _aplicar_sla(chamado)

    agora = timezone.now()
    if status_novo != status_antes:
        _mudar_status(chamado, status_antes, status_novo, agora)
    chamado.save()

    for campo in Chamado.CAMPOS_AUDITADOS:
        novo = valor_auditado(chamado, campo)
        if novo != antes[campo]:
            _historico(chamado, usuario, campo, novo, antes[campo])
    _historico_detalhes(chamado, usuario, detalhes_antes)
    return chamado


def _mudar_status(chamado, antes, novo, agora):
    S = Chamado.Status
    abertas = chamado.ordens.exclude(status__in=["FECHADA", "CANCELADA"])
    if novo in Chamado.ENCERRADOS and abertas.exists():
        raise ValueError("Feche ou cancele as OSs deste chamado antes de encerra-lo.")
    if novo == S.RESOLVIDO and not (chamado.nota_resolucao.strip() and chamado.categoria_encerramento):
        raise ValueError("Para resolver, informe a nota de resolucao e a categoria de encerramento.")

    if antes == S.NOVO:                      # saiu da fila de triagem = primeira resposta
        _marcar_primeira_resposta(chamado, agora)
    if antes == S.PENDENTE_CLIENTE and chamado.pausado_desde:   # relogio do SLA volta a correr
        chamado.tempo_pausado += agora - chamado.pausado_desde
        chamado.pausado_desde = None
    if novo == S.PENDENTE_CLIENTE:           # relogio do SLA para
        chamado.pausado_desde = agora
    chamado.resolvido_em = agora if novo == S.RESOLVIDO else None


@transaction.atomic
def comentar(chamado, usuario, texto):
    if not texto.strip():
        raise ValueError("Comentario vazio.")
    chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
    if not chamado.primeira_resposta_em:
        _marcar_primeira_resposta(chamado, timezone.now())
        chamado.save(update_fields=["primeira_resposta_em"])
    return ComentarioChamado.objects.create(chamado=chamado, autor=usuario, texto=texto.strip())


def anexar(chamado, usuario, arquivo, descricao=""):
    try:
        validar_anexo(arquivo)      # tipo, tamanho e conteudo (vale para tela e API)
    except ValidationError as e:
        raise ValueError(" ".join(e.messages)) from None
    return AnexoChamado.objects.create(chamado=chamado, arquivo=arquivo, descricao=descricao, enviado_por=usuario)


@transaction.atomic
def gerar_os(chamado, usuario, **dados):
    """Triagem aprovada: o chamado vira uma ordem de servico (execucao). Chamado novo passa a 'em atendimento'."""
    chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
    dados.setdefault("titulo", chamado.titulo)
    dados.setdefault("prioridade", chamado.prioridade)
    ordem = ordens.abrir_os(usuario, chamado, **dados)
    _historico(chamado, usuario, "os", f"OS {ordem.numero} gerada")
    if chamado.status in (Chamado.Status.NOVO, Chamado.Status.PENDENTE_CLIENTE):
        atualizar_chamado(chamado, usuario, status=Chamado.Status.EM_ATENDIMENTO)
    return ordem


def _horas(texto):
    try:
        valor = Decimal(str(texto).replace(",", ".").strip())
    except InvalidOperation:
        raise ValueError(f"'{texto}' nao e um numero de horas.") from None
    if valor <= 0:
        raise ValueError("Os prazos precisam ser maiores que zero.")
    return valor


@transaction.atomic
def salvar_tabela_sla(cliente, valores):
    """Grava a tabela de SLA (tipo x prioridade) do contrato do cliente, ou a padrao se cliente=None.

    valores: {(tipo, prioridade): (horas_resposta, horas_solucao)}. Celula vazia = sem prazo proprio
    (no contrato, passa a valer o padrao). Vale so para atividades abertas depois da mudanca.
    """
    erros = []
    for (tipo, prioridade), (resposta, solucao) in valores.items():
        rotulo = f"{Tipo(tipo).label} / {Prioridade(prioridade).label}"
        existente = PoliticaSLA.objects.filter(cliente=cliente, tipo=tipo, prioridade=prioridade)
        if not str(resposta).strip() and not str(solucao).strip():
            existente.delete()
            continue
        try:
            horas_resposta, horas_solucao = _horas(resposta), _horas(solucao)
            if horas_solucao < horas_resposta:
                raise ValueError("a solucao nao pode ter prazo menor que a primeira resposta.")
        except ValueError as e:
            erros.append(f"{rotulo}: {e}")
            continue
        PoliticaSLA.objects.update_or_create(cliente=cliente, tipo=tipo, prioridade=prioridade, defaults={
            "horas_resposta": horas_resposta, "horas_solucao": horas_solucao})
    if erros:   # a excecao desfaz a transacao inteira: ou grava a tabela toda, ou nada
        raise ValueError(" ".join(erros))
