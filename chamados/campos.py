"""Campos especificos de cada tipo de chamado (formulario por categoria).

Cada tipo coleta so o que muda a triagem daquele tipo. Os valores ficam em Chamado.detalhes (JSON).
Para mudar o formulario de um tipo, basta editar a lista abaixo: nao precisa de migracao.
"""
from dataclasses import dataclass
from datetime import date, datetime

from django.utils import timezone

from .models import Tipo

TEXTO, TEXTO_LONGO, DATA, DATA_HORA, ESCOLHA = "texto", "texto_longo", "data", "data_hora", "escolha"


@dataclass(frozen=True)
class Campo:
    nome: str
    rotulo: str
    tipo: str = TEXTO
    obrigatorio: bool = False
    opcoes: tuple = ()
    ajuda: str = ""
    largura: str = "col-md-6"
    placeholder: str = ""


LOCAL_EXATO = Campo("local_exato", "Localização exata", largura="col-md-4", placeholder="Andar, sala, rack")

TIPOS = {
    # Um so formulario de manutencao: serve para falha (incidente/corretiva) e para rotina programada (preventiva)
    Tipo.MANUTENCAO: {
        "titulo": "Manutenção: [equipamento ou serviço] em [local]",
        "campos": [
            Campo("sintoma", "O que acontece / o que precisa ser feito", TEXTO_LONGO, True, largura="col-12",
                  placeholder="Sem sinal, lentidão, quedas, equipamento danificado, rotina de inspeção"),
            Campo("afetados", "Quem está afetado", ESCOLHA, True, largura="col-md-4", opcoes=(
                ("NINGUEM", "Ninguém (manutenção programada)"), ("USUARIO", "Um usuário"),
                ("SETOR", "Uma equipe / setor"), ("UNIDADE", "Toda a unidade"), ("VARIAS", "Várias unidades"))),
            Campo("desde_quando", "Desde quando", DATA_HORA, largura="col-md-4",
                  ajuda="Quando o problema começou (vazio se for programada)"),
            Campo("risco", "Risco envolvido", ESCOLHA, largura="col-md-4", opcoes=(
                ("NENHUM", "Nenhum aparente"), ("OPERACIONAL", "Operacional"),
                ("SEGURANCA", "Segurança das pessoas"))),
            LOCAL_EXATO,
            Campo("mensagem_erro", "Mensagem de erro / alarme", largura="col-md-4",
                  placeholder="Texto exato do erro ou alarme"),
            Campo("alternativa", "Alternativa em uso", largura="col-md-4", placeholder="Ex.: 4G de contingência",
                  ajuda="Deixe vazio se não houver"),
            Campo("ja_tentado", "O que já foi tentado", largura="col-12",
                  placeholder="Reinicio do equipamento, teste de outro ponto"),
        ],
    },
    # Instalacao reune ativacao de servico novo e execucao de servico avulso
    Tipo.INSTALACAO: {
        "titulo": "Instalação: [serviço] para [cliente final] em [local]",
        "campos": [
            Campo("servico_contratado", "Serviço", ESCOLHA, True, largura="col-md-4", opcoes=(
                ("LINK_DEDICADO", "Link dedicado"), ("BANDA_LARGA", "Banda larga"), ("MPLS", "MPLS / VPN"),
                ("VOIP", "VoIP / telefonia"), ("RADIO", "Rádio"),
                ("EXECUCAO", "Execução de serviço (remanejamento, vistoria, configuração)"))),
            Campo("velocidade", "Velocidade / plano", largura="col-md-4", placeholder="Ex.: 500 Mbps"),
            Campo("pedido", "No do pedido / contrato", largura="col-md-4"),
            Campo("escopo", "O que será feito", TEXTO_LONGO, True, largura="col-12",
                  placeholder="Ativação, lançamento de fibra, instalação de equipamento, configuração"),
            LOCAL_EXATO,
            Campo("data_desejada", "Data desejada", DATA, largura="col-md-4"),
            Campo("prerequisitos", "Pré-requisitos", ESCOLHA, True, largura="col-md-4", opcoes=(
                ("OK", "Todos confirmados"), ("PENDENTE", "Há pendências"))),
            Campo("pendencias", "Pendências", largura="col-md-6",
                  placeholder="Energia, rack, tubulação, autorização do condomínio"),
            Campo("materiais", "Materiais previstos", largura="col-md-6", placeholder="ONT, roteador, cabos"),
            Campo("criterio_aceite", "Critério de aceite", TEXTO_LONGO, largura="col-12",
                  placeholder="Teste de velocidade/latência, certificação da fibra, termo de aceite assinado"),
        ],
    },
}

def campos_do_tipo(tipo):
    return TIPOS.get(tipo, {}).get("campos", [])


def rotulo(tipo, nome):
    return next((c.rotulo for c in campos_do_tipo(tipo) if c.nome == nome), nome)


def _vazio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def validar_detalhes(tipo, detalhes):
    """Valida e normaliza os detalhes de um tipo. Usado pelo services (vale para telas, admin e API)."""
    if not isinstance(detalhes, dict):
        raise ValueError("Detalhes do chamado em formato inválido.")
    limpos, faltando = {}, []
    for c in campos_do_tipo(tipo):
        valor = detalhes.get(c.nome)
        if _vazio(valor):
            if c.obrigatorio:
                faltando.append(c.rotulo)
            continue
        if isinstance(valor, (date, datetime)):
            valor = valor.isoformat()
        valor = str(valor).strip()
        if c.tipo == ESCOLHA and valor not in dict(c.opcoes):
            raise ValueError(f"Opção inválida em '{c.rotulo}'.")
        if c.tipo in (DATA, DATA_HORA):
            try:
                (datetime if c.tipo == DATA_HORA else date).fromisoformat(valor)
            except ValueError:
                raise ValueError(f"Data inválida em '{c.rotulo}'.") from None
        limpos[c.nome] = valor
    if faltando:
        raise ValueError("Preencha: " + ", ".join(faltando) + ".")
    return limpos


def formatar(campo, valor):
    if campo.tipo == ESCOLHA:
        return dict(campo.opcoes).get(valor, valor)
    if campo.tipo == DATA_HORA:
        dt = datetime.fromisoformat(valor)
        return f"{timezone.localtime(dt) if timezone.is_aware(dt) else dt:%d/%m/%Y %H:%M}"
    if campo.tipo == DATA:
        return f"{date.fromisoformat(valor):%d/%m/%Y}"
    return valor


def detalhes_legiveis(chamado):
    """[(campo, valor formatado)] na ordem do formulario, so os preenchidos."""
    return [(c, formatar(c, chamado.detalhes[c.nome])) for c in campos_do_tipo(chamado.tipo)
            if not _vazio(chamado.detalhes.get(c.nome))]
