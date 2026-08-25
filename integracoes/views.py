"""Endpoints para sistemas externos (autenticados por chave) e administração de integrações."""

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from almoxarifado import services as almox
from almoxarifado.models import Item, Solicitacao
from almoxarifado.serializers import ItemSerializer, NotaFiscalCreateSerializer, NotaFiscalSerializer, SolicitacaoSerializer
from chamados import services as cham
from chamados.models import Categoria
from chamados.serializers import ChamadoDetailSerializer
from core.models import CentroCusto
from core.permissions import EhAdministrador

from .authentication import ChaveDeSistemaAuthentication
from .idempotencia import IdempotenteMixin
from .models import EventoIntegracao, SistemaExterno, Webhook
from .permissions import TemEscopo
from .serializers import (
    ChamadoExternoSerializer,
    EventoSerializer,
    ItemSyncSerializer,
    SistemaExternoSerializer,
    SolicitacaoExternaSerializer,
    WebhookSerializer,
)


class _Externa(IdempotenteMixin, APIView):
    authentication_classes = [ChaveDeSistemaAuthentication]
    permission_classes = [TemEscopo]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "integracao"


class SolicitacaoExternaView(_Externa):
    """POST: cria solicitação de material em nome de um colaborador identificado pelo sistema externo."""

    escopo = "almoxarifado:escrever"

    def post(self, request):
        s = SolicitacaoExternaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        user = d["solicitante"]["user"]
        cc = None
        if d.get("centro_custo"):
            cc = CentroCusto.objects.filter(codigo=d["centro_custo"], ativo=True).first()
            if not cc:
                return Response({"centro_custo": ["Centro de custo não encontrado."]}, status=400)
        cc = cc or CentroCusto.objects.filter(setor=user.setor, ativo=True).first()
        if not cc:
            return Response({"centro_custo": ["Setor sem centro de custo ativo."]}, status=400)
        sol = almox.criar_solicitacao(
            solicitante=user, centro_custo=cc, os_ref=d["os_ref"], urgente=d["urgente"],
            origem=d["origem"][:12], itens=[{"item": i["item"], "quantidade": i["quantidade"]} for i in d["itens"]],
        )  # fmt: skip
        sol = Solicitacao.objects.select_related("setor", "solicitante", "centro_custo").prefetch_related("itens__item").get(pk=sol.pk)
        return Response(SolicitacaoSerializer(sol).data, status=status.HTTP_201_CREATED)


class ChamadoExternoView(_Externa):
    escopo = "chamados:escrever"

    def post(self, request):
        s = ChamadoExternoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        cat = Categoria.objects.filter(slug=d["categoria"]).first()
        if not cat:
            return Response({"categoria": ["Categoria não encontrada."]}, status=400)
        c = cham.abrir_chamado(solicitante=d["solicitante"]["user"], titulo=d["titulo"], descricao=d["descricao"],
                               categoria=cat, prioridade=d["prioridade"])  # fmt: skip
        return Response(ChamadoDetailSerializer(c).data, status=status.HTTP_201_CREATED)


class ItemSyncView(_Externa):
    """POST: lista de itens para upsert (cadastro mestre vindo de ERP)."""

    escopo = "almoxarifado:escrever"

    @transaction.atomic
    def post(self, request):
        s = ItemSyncSerializer(data=request.data, many=True)
        s.is_valid(raise_exception=True)
        criados, atualizados = 0, 0
        for d in s.validated_data:
            item = None
            if d.get("codigo_sankhya"):
                item = Item.objects.filter(codigo_sankhya=d["codigo_sankhya"]).first()
            if item is None and d.get("codigo"):
                item = Item.objects.filter(codigo=d["codigo"]).first()
            if item is None:
                faltando = [f for f in ("codigo", "descricao", "unidade", "setor_dono") if not d.get(f)]
                if faltando:
                    return Response({"erro": "campos_obrigatorios_para_criar", "faltando": faltando, "item": d.get("codigo") or d.get("codigo_sankhya")}, status=400)
                Item.objects.create(criado_por=request.user, **d)
                criados += 1
            else:
                for k, v in d.items():
                    setattr(item, k, v)
                item.save()
                atualizados += 1
        return Response({"criados": criados, "atualizados": atualizados})


class NotaFiscalExternaView(_Externa):
    escopo = "almoxarifado:escrever"

    def post(self, request):
        s = NotaFiscalCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        nota = almox.entrada_por_nota(usuario=request.user, **s.validated_data)
        return Response(NotaFiscalSerializer(nota).data, status=status.HTTP_201_CREATED)


class EstoqueExternoView(_Externa):
    escopo = "almoxarifado:ler"

    def get(self, request):
        from almoxarifado import selectors

        setor_sigla = request.query_params.get("setor")
        from core.models import Setor

        setor = Setor.objects.filter(sigla=setor_sigla).first() if setor_sigla else None
        qs = selectors.itens_com_saldo(setor) if setor else Item.objects.filter(ativo=True).select_related("setor_dono")
        return Response(ItemSerializer(qs.order_by("codigo")[:2000], many=True).data)


class EventosExternosView(_Externa):
    """Polling: eventos do próprio sistema (alternativa ao webhook). `?desde=<id>`."""

    escopo = "eventos:ler"

    def get(self, request):
        qs = EventoIntegracao.objects.filter(webhook__sistema=request.sistema_externo)
        if desde := request.query_params.get("desde"):
            qs = qs.filter(pk__gt=int(desde))
        return Response(EventoSerializer(qs.order_by("id")[:500], many=True).data)


# ---- administração (Admin, JWT) ----


class SistemaExternoViewSet(viewsets.ModelViewSet):
    queryset = SistemaExterno.objects.all()
    serializer_class = SistemaExternoSerializer
    permission_classes = [IsAuthenticated, EhAdministrador]
    pagination_class = None

    def perform_create(self, serializer):
        obj = serializer.save(criado_por=self.request.user)
        self._chave = obj.gerar_chave()
        obj.save(update_fields=["chave_hash", "prefixo_chave"])

    def create(self, request, *args, **kwargs):
        resp = super().create(request, *args, **kwargs)
        resp.data["chave"] = self._chave  # única vez em que a chave é exibida
        return resp

    @action(detail=True, methods=["post"], url_path="rotacionar-chave")
    def rotacionar_chave(self, request, pk=None):
        obj = self.get_object()
        chave = obj.gerar_chave()
        obj.save(update_fields=["chave_hash", "prefixo_chave"])
        return Response({"chave": chave, "prefixo_chave": obj.prefixo_chave})


class WebhookViewSet(viewsets.ModelViewSet):
    queryset = Webhook.objects.select_related("sistema")
    serializer_class = WebhookSerializer
    permission_classes = [IsAuthenticated, EhAdministrador]
    pagination_class = None

    @action(detail=True, methods=["get"])
    def eventos(self, request, pk=None):
        qs = self.get_object().entregas.order_by("-id")[:200]
        return Response(EventoSerializer(qs, many=True).data)
