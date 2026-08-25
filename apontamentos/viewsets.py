from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import papeis
from core.mixins import SetorScopedQuerysetMixin
from core.permissions import AcessoModulo, PodeAprovarHoras, papeis_de

from . import selectors, services
from .models import MotivoRetrabalho, TipoTrabalho
from .serializers import (
    ApontamentoSerializer,
    CronometroRespostaSerializer,
    DecisaoLoteSerializer,
    RecusaSerializer,
    IniciarCronometroSerializer,
    LancamentoManualSerializer,
    MotivoRetrabalhoSerializer,
    TipoTrabalhoSerializer,
)


class ApontamentoViewSet(SetorScopedQuerysetMixin, viewsets.GenericViewSet):
    modulo = "tarefa"
    permission_classes = [IsAuthenticated, AcessoModulo]
    queryset = selectors.base_listagem()
    serializer_class = ApontamentoSerializer
    filterset_fields = {"usuario": ["exact"], "tipo": ["exact"], "chamado": ["exact"],
                        "projeto": ["exact"], "inicio": ["date__gte", "date__lte"],
                        "pendente_aprovacao": ["exact"]}  # fmt: skip
    ordering_fields = ["inicio", "minutos"]
    campo_setor = "usuario__setor"

    def escopar_para_setor(self, qs, user):
        if papeis_de(user) & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}:
            return qs.filter(usuario__setor=user.setor)
        return qs.filter(usuario=user)

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(ApontamentoSerializer(page, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(ApontamentoSerializer(self.get_object()).data)

    def create(self, request):
        """Lançamento manual: inicio e fim obrigatórios; sempre para o próprio usuário."""
        s = LancamentoManualSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ap = services.criar_apontamento(usuario=request.user, **s.validated_data)
        ap = self.get_queryset().get(pk=ap.pk)
        return Response(ApontamentoSerializer(ap).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, PodeAprovarHoras])
    def aprovar(self, request, pk=None):
        ap = services.aprovar_apontamento(apontamento=self.get_object(), aprovador=request.user)
        return Response(ApontamentoSerializer(self.get_queryset().get(pk=ap.pk)).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, PodeAprovarHoras])
    def recusar(self, request, pk=None):
        s = RecusaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ap = services.recusar_apontamento(apontamento=self.get_object(), aprovador=request.user, motivo=s.validated_data["motivo"])
        return Response(ApontamentoSerializer(self.get_queryset().get(pk=ap.pk)).data)

    @action(detail=False, methods=["post"], url_path="decidir-lote",
            permission_classes=[IsAuthenticated, PodeAprovarHoras])  # fmt: skip
    def decidir_lote(self, request):
        s = DecisaoLoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        visiveis = set(self.get_queryset().filter(pk__in=d["ids"]).values_list("pk", flat=True))
        if visiveis != set(d["ids"]):
            return Response({"erro": "fora_do_escopo", "ids": sorted(set(d["ids"]) - visiveis)}, status=404)
        return Response(services.decidir_em_lote(ids=d["ids"], aprovador=request.user, aprovar=d["aprovar"], motivo=d["motivo"]))

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated, PodeAprovarHoras])
    def pendentes(self, request):
        qs = self.get_queryset().filter(pendente_aprovacao=True).order_by("inicio")
        if papeis.GERENTE_SETOR in papeis_de(request.user) and not (
            papeis_de(request.user) & {papeis.GERENTE_TI, papeis.ADMINISTRADOR}
        ):
            qs = qs.filter(Q(usuario__setor=request.user.setor))
        return Response(ApontamentoSerializer(qs, many=True).data)


class CronometroView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        aberto = services.cronometro_aberto(request.user)
        return Response(ApontamentoSerializer(aberto).data if aberto else None)


class IniciarCronometroView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = IniciarCronometroSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        novo, pausado = services.iniciar_cronometro(usuario=request.user, **s.validated_data)
        novo = selectors.base_listagem().get(pk=novo.pk)
        dados = CronometroRespostaSerializer({"apontamento": novo, "pausado": pausado}).data
        return Response(dados, status=status.HTTP_201_CREATED)


class PararCronometroView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ap = services.parar_cronometro(usuario=request.user)
        return Response(ApontamentoSerializer(selectors.base_listagem().get(pk=ap.pk)).data)


class TipoTrabalhoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TipoTrabalho.objects.all()
    serializer_class = TipoTrabalhoSerializer
    pagination_class = None


class MotivoRetrabalhoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MotivoRetrabalho.objects.all()
    serializer_class = MotivoRetrabalhoSerializer
    pagination_class = None
