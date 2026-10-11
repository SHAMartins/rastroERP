from rest_framework import serializers

from chamados.models import AnexoChamado, Chamado, ComentarioChamado, HistoricoChamado, PoliticaSLA
from clientes.models import Cliente, Servico
from estoque.models import ItemSerie, MovimentacaoEstoque, Produto
from ordens.models import Anexo, Comentario, HistoricoAlteracao, OrdemServico


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = "__all__"


class PoliticaSLASerializer(serializers.ModelSerializer):
    class Meta:
        model = PoliticaSLA
        fields = "__all__"


class ServicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Servico
        fields = "__all__"


class ProdutoSerializer(serializers.ModelSerializer):
    saldo = serializers.IntegerField(read_only=True)

    class Meta:
        model = Produto
        fields = "__all__"


class ItemSerieSerializer(serializers.ModelSerializer):
    ordem = serializers.IntegerField(source="saida.ordem_id", read_only=True, allow_null=True)

    class Meta:
        model = ItemSerie
        fields = ["id", "produto", "numero_serie", "status", "entrada", "saida", "ordem"]


class MovimentacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimentacaoEstoque
        fields = "__all__"
        read_only_fields = ["usuario", "ordem", "criado_em"]


class ComentarioSerializer(serializers.ModelSerializer):
    autor = serializers.StringRelatedField()

    class Meta:
        model = Comentario
        fields = ["id", "autor", "texto", "criado_em"]


class AnexoSerializer(serializers.ModelSerializer):
    enviado_por = serializers.StringRelatedField()
    download = serializers.CharField(source="url_download", read_only=True)

    class Meta:
        model = Anexo
        fields = ["id", "arquivo", "download", "descricao", "enviado_por", "enviado_em"]
        extra_kwargs = {"arquivo": {"write_only": True}}


class HistoricoSerializer(serializers.ModelSerializer):
    usuario = serializers.StringRelatedField()

    class Meta:
        model = HistoricoAlteracao
        fields = ["alterado_em", "usuario", "campo", "valor_anterior", "valor_novo"]


class OrdemSerializer(serializers.ModelSerializer):
    endereco = serializers.CharField(read_only=True)
    coordenadas = serializers.CharField(read_only=True)
    comentarios = ComentarioSerializer(many=True, read_only=True)
    anexos = AnexoSerializer(many=True, read_only=True)
    historico = HistoricoSerializer(many=True, read_only=True)
    materiais = MovimentacaoSerializer(source="movimentacoes", many=True, read_only=True)

    class Meta:
        model = OrdemServico
        fields = ["id", "numero", "chamado", "cliente", "servico", "titulo", "descricao",
                  "prioridade", "status", "responsavel", "data_abertura", "data_agendada",
                  "data_fechamento", "endereco", "coordenadas",
                  "comentarios", "anexos", "materiais", "historico"]
        read_only_fields = ["numero", "cliente", "data_abertura", "data_fechamento"]

    def get_fields(self):
        campos = super().get_fields()
        if self.instance is not None:          # o chamado de origem so e informado na criacao
            campos["chamado"].read_only = True
        return campos


class MaterialEntradaSerializer(serializers.Serializer):
    produto_id = serializers.IntegerField()
    quantidade = serializers.IntegerField(min_value=1, required=False, help_text="Opcional se informar numeros_serie")
    numeros_serie = serializers.ListField(child=serializers.CharField(), required=False,
                                          help_text="Obrigatorio para produto que controla numero de serie")


class ComentarioChamadoSerializer(serializers.ModelSerializer):
    autor = serializers.StringRelatedField()

    class Meta:
        model = ComentarioChamado
        fields = ["id", "autor", "texto", "criado_em"]


class AnexoChamadoSerializer(serializers.ModelSerializer):
    enviado_por = serializers.StringRelatedField()
    download = serializers.CharField(source="url_download", read_only=True)

    class Meta:
        model = AnexoChamado
        fields = ["id", "arquivo", "download", "descricao", "enviado_por", "enviado_em"]
        extra_kwargs = {"arquivo": {"write_only": True}}


class HistoricoChamadoSerializer(serializers.ModelSerializer):
    usuario = serializers.StringRelatedField()

    class Meta:
        model = HistoricoChamado
        fields = ["alterado_em", "usuario", "campo", "valor_anterior", "valor_novo"]


class ChamadoSerializer(serializers.ModelSerializer):
    """'detalhes' traz os campos especificos do tipo (ver chamados/campos.py), ex.: {"sintoma": "...",
    "desde_quando": "2026-10-11T08:00", "afetados": "UNIDADE"} para incidente."""
    situacao_sla = serializers.CharField(read_only=True)
    prazo_solucao_efetivo = serializers.DateTimeField(read_only=True)
    ordens = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    comentarios = ComentarioChamadoSerializer(many=True, read_only=True)
    anexos = AnexoChamadoSerializer(many=True, read_only=True)
    historico = HistoricoChamadoSerializer(many=True, read_only=True)

    class Meta:
        model = Chamado
        fields = ["id", "numero", "tipo", "cliente", "titulo", "detalhes", "solicitante_nome", "solicitante_contato",
                  "cliente_final", "endereco", "latitude", "longitude", "contato_local", "janela_acesso", "ativo",
                  "impacto", "urgencia", "prioridade", "status", "responsavel",
                  "aberto_em", "prazo_resposta", "prazo_solucao", "prazo_solucao_efetivo", "primeira_resposta_em",
                  "resolvido_em", "tempo_pausado", "situacao_sla",
                  "nota_resolucao", "causa", "categoria_encerramento",
                  "ordens", "comentarios", "anexos", "historico"]
        read_only_fields = ["numero", "prioridade", "aberto_em", "prazo_resposta", "prazo_solucao",
                            "primeira_resposta_em", "resolvido_em", "tempo_pausado"]

    def get_fields(self):
        campos = super().get_fields()
        if self.instance is None:              # todo chamado nasce "novo"
            campos["status"].read_only = True
        else:                                  # o cliente define o SLA: nao muda depois
            campos["cliente"].read_only = True
        return campos


class GerarOSSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdemServico
        fields = ["titulo", "descricao", "servico", "prioridade", "responsavel", "data_agendada"]
        extra_kwargs = {"titulo": {"required": False}, "prioridade": {"required": False}}
