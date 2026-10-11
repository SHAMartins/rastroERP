"""Regras de negocio das OSs. Usadas pela interface, pelo admin e pela API."""
from django.db import transaction
from django.utils import timezone

from estoque import services as estoque

from chamados.models import Chamado

from .models import Comentario, HistoricoAlteracao, OrdemServico


def _gerar_numero():
    ano = timezone.now().year
    ultimo = (OrdemServico.objects.select_for_update()
              .filter(numero__startswith=f"{ano}-").order_by("-numero").first())
    seq = int(ultimo.numero.split("-")[1]) + 1 if ultimo else 1
    return f"{ano}-{seq:05d}"          # ex.: 2026-00001


def valor_auditado(obj, campo):
    """Valor legivel de um campo para o historico (usa o rotulo das choices quando existe)."""
    v = getattr(obj, campo)
    if v is None:
        return ""
    display = getattr(obj, f"get_{campo}_display", None)
    return str(display() if display else v)


def _validar_servico(cliente_id, servico=None):
    """Servico especifico de um cliente nao pode ser usado em OS de outro cliente."""
    if servico is not None and servico.cliente_id and servico.cliente_id != cliente_id:
        raise ValueError("Este servico e exclusivo de outro cliente.")


@transaction.atomic
def abrir_os(usuario, chamado, **dados):
    """Toda OS nasce de um chamado. Cliente e endereco vem dele. Use chamados.services.gerar_os."""
    if chamado.status in Chamado.ENCERRADOS:
        raise ValueError("Nao e possivel gerar OS para chamado resolvido ou cancelado.")
    _validar_servico(chamado.cliente_id, dados.get("servico"))
    dados.pop("cliente", None)
    ordem = OrdemServico(numero=_gerar_numero(), criado_por=usuario, chamado=chamado,
                         cliente_id=chamado.cliente_id, **dados)
    ordem.save()
    HistoricoAlteracao.objects.create(ordem=ordem, usuario=usuario, campo="criacao",
                                      valor_novo=f"OS aberta com status {ordem.get_status_display()}")
    return ordem


@transaction.atomic
def atualizar_os(ordem, usuario, **dados):
    """Aplica as alteracoes e registra uma linha de historico por campo alterado."""
    ordem = OrdemServico.objects.select_for_update().get(pk=ordem.pk)
    if ordem.status in (OrdemServico.Status.FECHADA, OrdemServico.Status.CANCELADA) \
            and dados.get("status", ordem.status) == ordem.status:
        raise ValueError("OS fechada/cancelada nao pode ser editada. Reabra antes.")
    _validar_servico(ordem.cliente_id, dados.get("servico"))

    antes = {c: valor_auditado(ordem, c) for c in OrdemServico.CAMPOS_AUDITADOS}
    for campo, valor in dados.items():
        if campo in OrdemServico.CAMPOS_AUDITADOS:
            setattr(ordem, campo, valor)
    if ordem.status == OrdemServico.Status.FECHADA and not ordem.data_fechamento:
        ordem.data_fechamento = timezone.now()
    elif ordem.status != OrdemServico.Status.FECHADA:
        ordem.data_fechamento = None
    ordem.save()

    for campo in OrdemServico.CAMPOS_AUDITADOS:
        novo = valor_auditado(ordem, campo)
        if novo != antes[campo]:
            HistoricoAlteracao.objects.create(ordem=ordem, usuario=usuario, campo=campo,
                                              valor_anterior=antes[campo], valor_novo=novo)
    return ordem


def comentar(ordem, usuario, texto):
    if not texto.strip():
        raise ValueError("Comentario vazio.")
    return Comentario.objects.create(ordem=ordem, autor=usuario, texto=texto.strip())


@transaction.atomic
def registrar_material(ordem, usuario, produto_id, quantidade=None, numeros_serie=None):
    """Integracao OS -> Estoque: o material usado gera saida rastreavel ligada a OS (e a unidade, se tiver serie)."""
    if ordem.status in (OrdemServico.Status.FECHADA, OrdemServico.Status.CANCELADA):
        raise ValueError("Nao e possivel lancar material em OS fechada/cancelada.")
    mov = estoque.baixar_para_os(produto_id, quantidade, ordem, usuario, numeros_serie)
    series = estoque.ler_series(numeros_serie)
    texto = f"{-mov.quantidade} {mov.produto.unidade} de {mov.produto.nome}"
    HistoricoAlteracao.objects.create(ordem=ordem, usuario=usuario, campo="material",
                                      valor_novo=texto + (f" (SN {', '.join(series)})" if series else ""))
    return mov
