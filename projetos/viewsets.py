from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.mixins import SetorScopedQuerysetMixin
from core.permissions import AcessoModulo

from . import selectors, services
from .models import FASES_KANBAN
from .serializers import (
    AlocacaoEntradaSerializer,
    AlocacaoSerializer,
    MarcoSerializer,
    MoverFaseSerializer,
    ProjetoEntradaSerializer,
    ProjetoSerializer,
)


class ProjetoViewSet(SetorScopedQuerysetMixin, viewsets.GenericViewSet):
    modulo = "projetos"
    permission_classes = [IsAuthenticated, AcessoModulo]
    queryset = selectors.base_listagem()
    serializer_class = ProjetoSerializer
    filterset_fields = ["fase", "setor_solicitante", "responsavel"]
    ordering_fields = ["nome", "fim_previsto", "criado_em"]
    pagination_class = None
    campo_setor = "setor_solicitante"

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        if request.query_params.get("historico") in ("true", "1"):
            return Response(ProjetoSerializer(selectors.historico(qs), many=True).data)
        abertos = qs.filter(fase__in=FASES_KANBAN).order_by("fim_previsto", "nome")
        return Response({
            "kpis": selectors.kpis(abertos),
            "colunas": {fase: ProjetoSerializer(ps, many=True).data for fase, ps in selectors.kanban(abertos).items()},
        })  # fmt: skip

    def retrieve(self, request, pk=None):
        return Response(ProjetoSerializer(self.get_object()).data)

    def create(self, request):
        s = ProjetoEntradaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        p = services.criar_projeto(usuario=request.user, **s.validated_data)
        return Response(ProjetoSerializer(self.get_queryset().get(pk=p.pk)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        s = ProjetoEntradaSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        p = services.editar_projeto(projeto=self.get_object(), usuario=request.user, **s.validated_data)
        return Response(ProjetoSerializer(self.get_queryset().get(pk=p.pk)).data)

    @action(detail=True, methods=["post"])
    def fase(self, request, pk=None):
        s = MoverFaseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        p = services.mover_fase(projeto=self.get_object(), para=d["fase"], usuario=request.user,
                                encerrado_em=d.get("encerrado_em"), situacao_final=d["situacao_final"])  # fmt: skip
        return Response(ProjetoSerializer(self.get_queryset().get(pk=p.pk)).data)

    @action(detail=True, methods=["get", "post"])
    def marcos(self, request, pk=None):
        p = self.get_object()
        if request.method == "GET":
            return Response(MarcoSerializer(p.marcos.order_by("previsto"), many=True).data)
        s = MarcoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        m = services.adicionar_marco(projeto=p, usuario=request.user, **s.validated_data)
        return Response(MarcoSerializer(m).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"marcos/(?P<marco_id>\d+)/concluir")
    def concluir_marco(self, request, pk=None, marco_id=None):
        from django.utils import timezone
        from django.utils.dateparse import parse_date

        p = self.get_object()
        marco = p.marcos.filter(pk=marco_id).first()
        if not marco:
            return Response(status=404)
        data = parse_date(request.data.get("concluido_em", "")) or timezone.localdate()
        return Response(MarcoSerializer(services.concluir_marco(marco=marco, usuario=request.user, concluido_em=data)).data)

    @action(detail=True, methods=["get", "post"])
    def alocacoes(self, request, pk=None):
        p = self.get_object()
        if request.method == "GET":
            return Response(AlocacaoSerializer(p.alocacoes.select_related("usuario"), many=True).data)
        s = AlocacaoEntradaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        a = services.alocar(projeto=p, usuario_alocado=s.validated_data["usuario"],
                            percentual=s.validated_data["percentual"], usuario=request.user)  # fmt: skip
        return Response(AlocacaoSerializer(a).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def capacidade(self, request):
        return Response(list(selectors.capacidade_alocada_por_pessoa()))
