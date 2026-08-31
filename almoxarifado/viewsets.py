from collections.abc import Sequence

from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import (
    BasePermission,
    IsAuthenticated,
    OperandHolder,
    SingleOperandHolder,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from core import papeis
from core.mixins import SetorScopedQuerysetMixin
from core.models import Setor
from core.permissions import AcessoModulo, AcessoModuloVisivel, papeis_de, ve_todos_setores

from . import selectors, services
from .models import (
    AlertaReposicao,
    Cotacao,
    Inventario,
    Item,
    Movimento,
    NotaFiscal,
    PropostaCotacao,
    Solicitacao,
    Transferencia,
)
from .permissions import PodeAprovarSolicitacao
from .serializers import (
    AtenderSerializer,
    ContagensEntradaSerializer,
    CotacaoCreateSerializer,
    CotacaoSerializer,
    EstoqueSerializer,
    InventarioCreateSerializer,
    InventarioSerializer,
    ItemSerializer,
    MovimentoCreateSerializer,
    MovimentoSerializer,
    NegarSerializer,
    NotaFiscalCreateSerializer,
    NotaFiscalSerializer,
    PropostaSerializer,
    SolicitacaoCreateSerializer,
    SolicitacaoSerializer,
    TransferenciaCreateSerializer,
    TransferenciaSerializer,
)

# Mesmo tipo que `APIView.permission_classes` declara; sem isto o mypy vê dois tipos
# diferentes para o atributo e recusa a herança múltipla.
_Permissao = type[BasePermission] | OperandHolder | SingleOperandHolder


class _Almox:
    """Mixin de módulo. Fora da hierarquia da APIView, então `permission_classes` precisa
    da anotação explícita — senão o mypy vê dois tipos diferentes para o mesmo atributo."""

    modulo = "almoxarifado"
    permission_classes: Sequence[_Permissao] = [IsAuthenticated, AcessoModulo]


def _setor_param(request):
    sid = request.query_params.get("setor")
    if sid and ve_todos_setores(request.user):
        return Setor.objects.filter(pk=sid).first()
    return request.user.setor


class ItemViewSet(_Almox, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Itens são cadastro global; o saldo vem anotado para o setor pedido (ou do usuário)."""

    serializer_class = ItemSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    ordering_fields = ["codigo", "descricao", "saldo"]

    def get_queryset(self):
        return selectors.itens_com_saldo(_setor_param(self.request)).order_by("codigo")

    def filter_queryset(self, qs):
        p = self.request.query_params
        if p.get("abaixo_minimo") in ("true", "1"):
            qs = qs.filter(abaixo_minimo=True)
        if busca := p.get("busca"):
            qs = qs.filter(Q(codigo__icontains=busca) | Q(descricao__icontains=busca) | Q(codigo_sankhya__icontains=busca))
        return super().filter_queryset(qs)

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(ItemSerializer(page, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(ItemSerializer(self.get_object()).data)

    def perform_create(self, serializer):
        serializer.save(criado_por=self.request.user)


class EstoqueView(_Almox, APIView):
    def get(self, request):
        setor = _setor_param(request)
        return Response({"setor": setor.sigla, "itens": EstoqueSerializer(selectors.estoque_por_setor(setor), many=True).data})


class MovimentoViewSet(_Almox, SetorScopedQuerysetMixin, viewsets.GenericViewSet):
    """GET e POST apenas — movimento é imutável."""

    queryset = Movimento.objects.select_related("item", "item__setor_dono", "setor", "usuario", "centro_custo")
    serializer_class = MovimentoSerializer
    filterset_fields = {"item": ["exact"], "tipo": ["exact"], "setor": ["exact"], "criado_em": ["date__gte", "date__lte"]}
    ordering_fields = ["criado_em"]
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(MovimentoSerializer(page, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(MovimentoSerializer(self.get_object()).data)

    def create(self, request):
        s = MovimentoCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if d["setor"] != request.user.setor and not ve_todos_setores(request.user):
            return Response({"erro": "fora_do_escopo", "mensagem": "Só movimenta o próprio setor."}, status=403)
        mov = services.registrar_movimento(usuario=request.user, **d)
        return Response(MovimentoSerializer(self.get_queryset().get(pk=mov.pk)).data, status=status.HTTP_201_CREATED)


class SolicitacaoViewSet(_Almox, SetorScopedQuerysetMixin, viewsets.GenericViewSet):
    queryset = Solicitacao.objects.select_related("setor", "solicitante", "centro_custo", "aprovada_por").prefetch_related(
        "itens__item__setor_dono"
    )
    serializer_class = SolicitacaoSerializer
    filterset_fields = ["status", "urgente", "setor"]

    def escopar_para_setor(self, qs, user):
        if papeis_de(user) & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}:
            return qs.filter(setor=user.setor)
        return qs.filter(solicitante=user)

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(SolicitacaoSerializer(page, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(SolicitacaoSerializer(self.get_object()).data)

    def create(self, request):
        s = SolicitacaoCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        sol = services.criar_solicitacao(solicitante=request.user, **s.validated_data)
        return Response(SolicitacaoSerializer(self.get_queryset().get(pk=sol.pk)).data, status=status.HTTP_201_CREATED)

    # Aprovar/negar é direito do PAPEL (gerente do setor), não do nível de escrita do
    # módulo — a matriz dá "V" ao gerente em almoxarifado, o que barrava todo POST dele.
    # Solicitação de outro setor não está no queryset e vira 404, não 403.
    @action(detail=True, methods=["post"],
            permission_classes=[IsAuthenticated, AcessoModuloVisivel, PodeAprovarSolicitacao])
    def aprovar(self, request, pk=None):
        sol = services.aprovar_solicitacao(solicitacao=self.get_object(), aprovador=request.user)
        return Response(SolicitacaoSerializer(self.get_queryset().get(pk=sol.pk)).data)

    @action(detail=True, methods=["post"],
            permission_classes=[IsAuthenticated, AcessoModuloVisivel, PodeAprovarSolicitacao])
    def negar(self, request, pk=None):
        s = NegarSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        sol = services.negar_solicitacao(solicitacao=self.get_object(), aprovador=request.user, motivo=s.validated_data["motivo"])
        return Response(SolicitacaoSerializer(self.get_queryset().get(pk=sol.pk)).data)

    @action(detail=True, methods=["post"])
    def atender(self, request, pk=None):
        s = AtenderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        quantidades = {int(k): v for k, v in s.validated_data["quantidades"].items()} or None
        sol = services.atender_solicitacao(solicitacao=self.get_object(), usuario=request.user, quantidades=quantidades)
        return Response(SolicitacaoSerializer(self.get_queryset().get(pk=sol.pk)).data)


class _SoComprasEscreve(_Almox):
    """NF, cotação e inventário: leitura pelo escopo; escrita só Compras/Admin (e Responsável no próprio setor)."""

    def escreve(self, request, setor=None) -> bool:
        meus = papeis_de(request.user)
        if meus & {papeis.COMPRAS, papeis.ADMINISTRADOR}:
            return True
        return papeis.RESPONSAVEL in meus and setor is not None and setor.pk == request.user.setor_id


class NotaFiscalViewSet(_SoComprasEscreve, SetorScopedQuerysetMixin, viewsets.GenericViewSet):
    queryset = NotaFiscal.objects.select_related("setor", "conferida_por").prefetch_related("itens__item__setor_dono")
    serializer_class = NotaFiscalSerializer
    filterset_fields = ["setor", "fornecedor"]

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(NotaFiscalSerializer(page, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(NotaFiscalSerializer(self.get_object()).data)

    def create(self, request):
        s = NotaFiscalCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not self.escreve(request, d["setor"]):
            return Response({"erro": "fora_do_escopo"}, status=403)
        nota = services.entrada_por_nota(usuario=request.user, **d)
        return Response(NotaFiscalSerializer(self.get_queryset().get(pk=nota.pk)).data, status=status.HTTP_201_CREATED)


class TransferenciaViewSet(_Almox, viewsets.GenericViewSet):
    queryset = Transferencia.objects.select_related("item", "item__setor_dono", "setor_origem", "setor_destino")
    serializer_class = TransferenciaSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if ve_todos_setores(u):
            return qs
        return qs.filter(Q(setor_origem=u.setor) | Q(setor_destino=u.setor))

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(TransferenciaSerializer(page, many=True).data)

    def create(self, request):
        s = TransferenciaCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if d["setor_origem"] != request.user.setor and not ve_todos_setores(request.user):
            return Response({"erro": "fora_do_escopo", "mensagem": "Só transfere a partir do próprio setor."}, status=403)
        t = services.transferir(usuario=request.user, **d)
        return Response(TransferenciaSerializer(self.get_queryset().get(pk=t.pk)).data, status=status.HTTP_201_CREATED)


class InventarioViewSet(_SoComprasEscreve, SetorScopedQuerysetMixin, viewsets.GenericViewSet):
    queryset = Inventario.objects.select_related("setor", "responsavel").prefetch_related("contagens__item__setor_dono")
    serializer_class = InventarioSerializer
    filterset_fields = ["setor", "status"]

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(InventarioSerializer(page, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(InventarioSerializer(self.get_object()).data)

    def create(self, request):
        s = InventarioCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not self.escreve(request, d["setor"]):
            return Response({"erro": "fora_do_escopo"}, status=403)
        inv = services.abrir_inventario(setor=d["setor"], responsavel=request.user, itens=d.get("itens"))
        return Response(InventarioSerializer(self.get_queryset().get(pk=inv.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"])
    def contagens(self, request, pk=None):
        inv = self.get_object()
        if not self.escreve(request, inv.setor):
            return Response({"erro": "fora_do_escopo"}, status=403)
        s = ContagensEntradaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        n = services.registrar_contagens(inventario=inv, contagens=s.validated_data["contagens"], usuario=request.user)
        return Response({"registradas": n, **InventarioSerializer(self.get_queryset().get(pk=inv.pk)).data})

    @action(detail=True, methods=["post"])
    def fechar(self, request, pk=None):
        inv = self.get_object()
        if not self.escreve(request, inv.setor):
            return Response({"erro": "fora_do_escopo"}, status=403)
        inv = services.fechar_inventario(inventario=inv, usuario=request.user)
        dados = InventarioSerializer(self.get_queryset().get(pk=inv.pk)).data
        dados["itens_divergentes"] = [c for c in dados["contagens"] if c["divergencia"] not in (None, "0.000")]
        return Response(dados)


class CotacaoViewSet(_SoComprasEscreve, viewsets.GenericViewSet):
    queryset = Cotacao.objects.select_related("item", "item__setor_dono").prefetch_related("propostas")
    serializer_class = CotacaoSerializer
    filterset_fields = ["status", "item"]

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(CotacaoSerializer(page, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(CotacaoSerializer(self.get_object()).data)

    def create(self, request):
        if not self.escreve(request):
            return Response({"erro": "fora_do_escopo"}, status=403)
        s = CotacaoCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cot = services.abrir_cotacao(usuario=request.user, **s.validated_data)
        return Response(CotacaoSerializer(self.get_queryset().get(pk=cot.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def propostas(self, request, pk=None):
        if not self.escreve(request):
            return Response({"erro": "fora_do_escopo"}, status=403)
        s = PropostaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        prop = services.registrar_proposta(cotacao=self.get_object(), usuario=request.user, **s.validated_data)
        return Response(PropostaSerializer(prop).data, status=status.HTTP_201_CREATED)


class EscolherPropostaView(_SoComprasEscreve, APIView):
    def post(self, request, pk):
        if not self.escreve(request):
            return Response({"erro": "fora_do_escopo"}, status=403)
        prop = PropostaCotacao.objects.filter(pk=pk).first()
        if not prop:
            return Response(status=404)
        return Response(PropostaSerializer(services.escolher_proposta(proposta=prop, usuario=request.user)).data)


class QRCodeView(_Almox, APIView):
    """Leitura por QR: `codigo` do item → item + saldo do setor do usuário (ou `?setor=`)."""

    def get(self, request, codigo):
        item = Item.objects.filter(codigo=codigo, ativo=True).select_related("setor_dono").first()
        if not item:
            return Response({"erro": "item_inexistente", "codigo": codigo}, status=404)
        setor = _setor_param(request)
        dados = ItemSerializer(item).data
        dados["saldo"] = selectors.saldo(item, setor)
        dados["abaixo_minimo"] = dados["saldo"] <= item.estoque_minimo
        dados["setor"] = setor.sigla
        return Response(dados)


class AlertasView(_Almox, APIView):
    """Fila de reposição (Compras)."""

    def get(self, request):
        qs = AlertaReposicao.objects.filter(resolvido_em__isnull=True).select_related("item", "setor")
        if not ve_todos_setores(request.user):
            qs = qs.filter(setor=request.user.setor)
        return Response([
            {"id": a.id, "item": a.item.codigo, "descricao": a.item.descricao, "setor": a.setor.sigla,
             "saldo": a.saldo, "minimo": a.minimo, "origem": a.origem, "criado_em": a.criado_em}
            for a in qs
        ])  # fmt: skip
