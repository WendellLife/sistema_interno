"""Views: validação de entrada, permissão, chamada de serviço, resposta. Sem regra aqui."""

from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import papeis
from core.mixins import SetorScopedQuerysetMixin
from core.permissions import AcessoModulo, EhAdministrador, eh_ti, papeis_de

from . import selectors, services
from .filters import ChamadoFilter
from .models import Categoria, Chamado, RegraSLA
from .serializers import (
    AnexoSerializer,
    CategoriaSerializer,
    ChamadoCreateSerializer,
    ChamadoDetailSerializer,
    ChamadoListSerializer,
    ChamadoUpdateSerializer,
    ComentarioSerializer,
    HistoricoSerializer,
    RegraSLASerializer,
    TransicaoSerializer,
)


class ChamadoViewSet(SetorScopedQuerysetMixin, viewsets.GenericViewSet):
    modulo = "tarefas"
    permission_classes = [IsAuthenticated, AcessoModulo]
    queryset = selectors.base_listagem()
    filterset_class = ChamadoFilter
    ordering_fields = ["criado_em", "sla_previsto", "prioridade", "status"]
    campo_setor = "setor_origem"

    def escopar_para_setor(self, qs, user):
        # Colaborador: só os que abriu ou é responsável. Responsável/Gerente: o setor inteiro.
        meus = papeis_de(user)
        if meus & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}:
            return qs.filter(setor_origem=user.setor)
        return qs.filter(Q(solicitante=user) | Q(responsavel=user))

    def get_serializer_class(self):
        return {
            "list": ChamadoListSerializer,
            "create": ChamadoCreateSerializer,
            "partial_update": ChamadoUpdateSerializer,
            "transicoes": TransicaoSerializer,
            "comentarios": ComentarioSerializer,
            "anexos": AnexoSerializer,
            "historico": HistoricoSerializer,
        }.get(self.action, ChamadoDetailSerializer)

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        dados = ChamadoListSerializer(page, many=True).data
        resposta = self.get_paginated_response(dados)
        resposta.data["resumo"] = selectors.resumo_central(self.get_queryset())
        return resposta

    def retrieve(self, request, pk=None):
        return Response(ChamadoDetailSerializer(self.get_object()).data)

    def create(self, request):
        s = ChamadoCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        chamado = services.abrir_chamado(solicitante=request.user, **s.validated_data)
        return Response(ChamadoDetailSerializer(chamado).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        chamado = self.get_object()
        s = ChamadoUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if "prioridade" in d:
            chamado = services.alterar_prioridade(
                chamado=chamado, prioridade=d.pop("prioridade"), usuario=request.user
            )
        if "responsavel" in d:
            chamado = services.atribuir(
                chamado=chamado, responsavel=d.pop("responsavel"), usuario=request.user
            )
        if d:
            chamado = services.editar(chamado=chamado, usuario=request.user, **d)
        chamado = self.get_queryset().get(pk=chamado.pk)
        return Response(ChamadoDetailSerializer(chamado).data)

    @action(detail=True, methods=["post"])
    def transicoes(self, request, pk=None):
        chamado = self.get_object()
        s = TransicaoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        chamado = services.transicionar(
            chamado=chamado,
            para=s.validated_data["status"],
            usuario=request.user,
            comentario=s.validated_data["comentario"],
        )
        chamado = self.get_queryset().get(pk=chamado.pk)
        return Response(ChamadoDetailSerializer(chamado).data)

    @action(detail=True, methods=["get", "post"])
    def comentarios(self, request, pk=None):
        chamado = self.get_object()
        if request.method == "GET":
            qs = chamado.comentarios.select_related("autor")
            if not eh_ti(request.user):
                qs = qs.filter(interno=False)
            return Response(ComentarioSerializer(qs, many=True).data)
        s = ComentarioSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        interno = bool(s.validated_data.get("interno")) and eh_ti(request.user)
        c = services.comentar(
            chamado=chamado, autor=request.user, texto=s.validated_data["texto"], interno=interno
        )
        return Response(ComentarioSerializer(c).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser, FormParser])
    def anexos(self, request, pk=None):
        chamado = self.get_object()
        if request.method == "GET":
            return Response(AnexoSerializer(chamado.anexos.all(), many=True).data)
        s = AnexoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        a = services.anexar(chamado=chamado, usuario=request.user, arquivo=s.validated_data["arquivo"])
        return Response(AnexoSerializer(a).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def historico(self, request, pk=None):
        qs = self.get_object().historico.select_related("usuario")
        return Response(HistoricoSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="risco-sla")
    def risco_sla(self, request):
        ids = [c.pk for c in selectors.em_risco_de_sla()]
        qs = self.get_queryset().filter(pk__in=ids).order_by("sla_previsto")
        return Response(ChamadoListSerializer(qs, many=True).data)


class _ConfigViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                     mixins.CreateModelMixin, viewsets.GenericViewSet):  # fmt: skip
    """GET para todos; escrita só Admin (tela 'SLA e permissões')."""

    pagination_class = None

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), EhAdministrador()]


class CategoriaViewSet(_ConfigViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer


class RegraSLAViewSet(_ConfigViewSet):
    queryset = RegraSLA.objects.select_related("categoria")
    serializer_class = RegraSLASerializer

    def perform_update(self, serializer):
        from core.auditoria import registrar

        antes = {"horas_uteis": serializer.instance.horas_uteis}
        obj = serializer.save()
        registrar(
            usuario=self.request.user,
            acao="sla.alterar",
            objeto=obj,
            antes=antes,
            depois={"horas_uteis": obj.horas_uteis},
        )
