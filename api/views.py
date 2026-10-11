from django.core.exceptions import ValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response

from chamados import services as chamados
from chamados.models import Chamado, PoliticaSLA
from clientes.models import Cliente, Servico
from estoque.models import ItemSerie, MovimentacaoEstoque, Produto
from estoque.services import EstoqueInsuficiente
from ordens import services
from ordens.models import Anexo, OrdemServico
from seguranca.arquivos import validar_anexo
from seguranca.drf import EscritaComPermissao, OperaASuaOS, PermissaoPorAcao

from . import serializers as s

ERROS = (ValueError, EstoqueInsuficiente, Produto.DoesNotExist)
# Cadastros: leitura para todos; criar/alterar exige a permissao do model (perfil). Sem DELETE.
CADASTRO = {"permission_classes": [IsAuthenticated, DjangoModelPermissions],
            "http_method_names": ["get", "post", "put", "patch"]}


class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = s.ClienteSerializer
    permission_classes = CADASTRO["permission_classes"]
    http_method_names = CADASTRO["http_method_names"]


class PoliticaSLAViewSet(viewsets.ModelViewSet):
    """Prazos de SLA. Sem cliente = padrao geral; com cliente = contrato daquele cliente."""
    queryset = PoliticaSLA.objects.select_related("cliente")
    serializer_class = s.PoliticaSLASerializer
    permission_classes = [IsAuthenticated, EscritaComPermissao]
    permissao_escrita = "chamados.gerenciar_sla"


class ServicoViewSet(viewsets.ModelViewSet):
    queryset = Servico.objects.all()
    serializer_class = s.ServicoSerializer
    permission_classes = CADASTRO["permission_classes"]
    http_method_names = CADASTRO["http_method_names"]


class ProdutoViewSet(viewsets.ModelViewSet):
    queryset = Produto.objects.all()
    serializer_class = s.ProdutoSerializer
    permission_classes = CADASTRO["permission_classes"]
    http_method_names = CADASTRO["http_method_names"]


class ItemSerieViewSet(viewsets.ReadOnlyModelViewSet):
    """Unidades com numero de serie (somente leitura: nascem e mudam pelas movimentacoes).
    Filtros: ?numero_serie=, ?produto=, ?status=."""
    serializer_class = s.ItemSerieSerializer

    def get_queryset(self):
        itens = ItemSerie.objects.select_related("saida")
        for campo in ("numero_serie", "produto", "status"):
            if self.request.query_params.get(campo):
                itens = itens.filter(**{campo: self.request.query_params[campo]})
        return itens


class MovimentacaoViewSet(viewsets.ReadOnlyModelViewSet):
    """Somente leitura: o historico de estoque nao pode ser alterado."""
    queryset = MovimentacaoEstoque.objects.all()
    serializer_class = s.MovimentacaoSerializer


class OrdemViewSet(viewsets.ModelViewSet):
    queryset = OrdemServico.objects.select_related("cliente", "chamado").prefetch_related(
        "comentarios", "anexos", "historico", "movimentacoes")
    serializer_class = s.OrdemSerializer
    http_method_names = ["get", "post", "patch"]   # sem DELETE: OS e cancelada, nunca apagada
    permission_classes = [IsAuthenticated, PermissaoPorAcao, OperaASuaOS]
    permissoes_por_acao = {"create": "chamados.gerar_os"}

    def create(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        dados = dict(ser.validated_data)
        try:
            ordem = chamados.gerar_os(dados.pop("chamado"), request.user, **dados)
        except ERROS as e:
            return Response({"erro": str(e)}, status=400)
        return Response(self.get_serializer(ordem).data, status=201)

    def partial_update(self, request, pk=None):
        ser = self.get_serializer(self.get_object(), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        try:
            ordem = services.atualizar_os(self.get_object(), request.user, **ser.validated_data)
        except ERROS as e:
            return Response({"erro": str(e)}, status=400)
        return Response(self.get_serializer(ordem).data)

    @extend_schema(request=s.ComentarioSerializer, responses=s.ComentarioSerializer)
    @action(detail=True, methods=["post"])
    def comentar(self, request, pk=None):
        try:
            c = services.comentar(self.get_object(), request.user, request.data.get("texto", ""))
        except ValueError as e:
            return Response({"erro": str(e)}, status=400)
        return Response(s.ComentarioSerializer(c).data, status=201)

    @extend_schema(request=s.AnexoSerializer, responses=s.AnexoSerializer)
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def anexar(self, request, pk=None):
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            return Response({"erro": "Envie o campo 'arquivo'."}, status=400)
        ordem = self.get_object()
        try:
            validar_anexo(arquivo)
        except ValidationError as e:
            return Response({"erro": " ".join(e.messages)}, status=400)
        a = Anexo.objects.create(ordem=ordem, arquivo=arquivo,
                                 descricao=request.data.get("descricao", ""), enviado_por=request.user)
        return Response(s.AnexoSerializer(a).data, status=201)

    @extend_schema(request=s.MaterialEntradaSerializer, responses=s.MovimentacaoSerializer)
    @action(detail=True, methods=["post"])
    def materiais(self, request, pk=None):
        ser = s.MaterialEntradaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            mov = services.registrar_material(self.get_object(), request.user, **ser.validated_data)
        except ERROS as e:
            return Response({"erro": str(e)}, status=400)
        return Response(s.MovimentacaoSerializer(mov).data, status=201)


class ChamadoViewSet(viewsets.ModelViewSet):
    """Chamados (o pedido). A execucao e feita por OSs geradas a partir deles."""
    queryset = Chamado.objects.select_related("cliente").prefetch_related(
        "ordens", "comentarios", "anexos", "historico")
    serializer_class = s.ChamadoSerializer
    http_method_names = ["get", "post", "patch"]   # sem DELETE: chamado e cancelado, nunca apagado
    permission_classes = [IsAuthenticated, PermissaoPorAcao]
    permissoes_por_acao = {"create": "chamados.add_chamado", "partial_update": "chamados.triar_chamado",
                           "gerar_os": "chamados.gerar_os"}

    def create(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            chamado = chamados.abrir_chamado(request.user, **ser.validated_data)
        except ValueError as e:
            return Response({"erro": str(e)}, status=400)
        return Response(self.get_serializer(chamado).data, status=201)

    def partial_update(self, request, pk=None):
        ser = self.get_serializer(self.get_object(), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        try:
            chamado = chamados.atualizar_chamado(self.get_object(), request.user, **ser.validated_data)
        except ValueError as e:
            return Response({"erro": str(e)}, status=400)
        return Response(self.get_serializer(chamado).data)

    @extend_schema(request=s.ComentarioChamadoSerializer, responses=s.ComentarioChamadoSerializer)
    @action(detail=True, methods=["post"])
    def comentar(self, request, pk=None):
        try:
            c = chamados.comentar(self.get_object(), request.user, request.data.get("texto", ""))
        except ValueError as e:
            return Response({"erro": str(e)}, status=400)
        return Response(s.ComentarioChamadoSerializer(c).data, status=201)

    @extend_schema(request=s.AnexoChamadoSerializer, responses=s.AnexoChamadoSerializer)
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def anexar(self, request, pk=None):
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            return Response({"erro": "Envie o campo 'arquivo'."}, status=400)
        try:
            a = chamados.anexar(self.get_object(), request.user, arquivo, request.data.get("descricao", ""))
        except ValueError as e:
            return Response({"erro": str(e)}, status=400)
        return Response(s.AnexoChamadoSerializer(a).data, status=201)

    @extend_schema(request=s.GerarOSSerializer, responses=s.OrdemSerializer)
    @action(detail=True, methods=["post"], url_path="gerar-os")
    def gerar_os(self, request, pk=None):
        ser = s.GerarOSSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            ordem = chamados.gerar_os(self.get_object(), request.user, **ser.validated_data)
        except ValueError as e:
            return Response({"erro": str(e)}, status=400)
        return Response(s.OrdemSerializer(ordem).data, status=201)
