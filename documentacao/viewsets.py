from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import papeis
from core.mixins import SetorScopedQuerysetMixin
from core.models import Setor
from core.permissions import AcessoModulo, papeis_de

from . import selectors, services
from .serializers import (
    DocumentoCreateSerializer,
    DocumentoSerializer,
    RascunhoSerializer,
    VersaoSerializer,
)


class DocumentoViewSet(SetorScopedQuerysetMixin, viewsets.GenericViewSet):
    modulo = "documentacao"
    permission_classes = [IsAuthenticated, AcessoModulo]
    queryset = selectors.base_listagem()
    serializer_class = DocumentoSerializer
    filterset_fields = ["chamado", "projeto", "secao"]
    pagination_class = None

    def escopar_para_setor(self, qs, user):
        meus = papeis_de(user)
        if meus & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}:
            return qs.filter(Q(chamado__setor_origem=user.setor) | Q(projeto__setor_solicitante=user.setor))
        return qs.filter(
            Q(chamado__solicitante=user) | Q(chamado__responsavel=user) | Q(projeto__responsavel=user)
        )

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset()).order_by("id")
        return Response(DocumentoSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(DocumentoSerializer(self.get_object()).data)

    def create(self, request):
        s = DocumentoCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        doc = services.obter_documento(criado_por=request.user, **s.validated_data)
        doc = self.get_queryset().get(pk=doc.pk)
        return Response(DocumentoSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"])
    def versoes(self, request, pk=None):
        doc = self.get_object()
        if request.method == "GET":
            return Response(VersaoSerializer(doc.versoes.select_related("autor"), many=True).data)
        s = RascunhoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        versao = services.criar_rascunho(documento=doc, conteudo=s.validated_data["conteudo"], autor=request.user)
        if s.validated_data["publicar"]:
            versao = services.publicar_versao(versao=versao, usuario=request.user)
        versao = doc.versoes.select_related("autor").get(pk=versao.pk)
        return Response(VersaoSerializer(versao).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"versoes/(?P<numero>\d+)/publicar")
    def publicar(self, request, pk=None, numero=None):
        doc = self.get_object()
        versao = doc.versoes.filter(numero=int(numero)).first()
        if not versao:
            return Response({"erro": "versao_inexistente"}, status=status.HTTP_404_NOT_FOUND)
        versao = services.publicar_versao(versao=versao, usuario=request.user)
        return Response(VersaoSerializer(doc.versoes.select_related("autor").get(pk=versao.pk)).data)

    @action(detail=False, methods=["get"])
    def cobertura(self, request):
        from django.utils.dateparse import parse_date

        setor = None
        if sid := request.query_params.get("setor"):
            setor = Setor.objects.filter(pk=sid).first()
        elif not papeis_de(request.user) & papeis.VE_TODOS_SETORES:
            setor = request.user.setor
        de = parse_date(request.query_params.get("de") or "")
        ate = parse_date(request.query_params.get("ate") or "")
        return Response(selectors.cobertura(setor=setor, de=de, ate=ate))

    @action(detail=False, methods=["get"], url_path="pendentes")
    def pendentes(self, request):
        from chamados.viewsets import ChamadoViewSet

        # mesmo escopo da central de tarefas
        vs = ChamadoViewSet(request=request)
        vs.request = request
        pares = selectors.documentacao_pendente(vs.get_queryset())
        return Response([
            {"id": c.id, "numero": c.numero, "titulo": c.titulo, "setor": c.setor_origem.sigla,
             "responsavel": c.responsavel.nome if c.responsavel else None,
             "sla_previsto": c.sla_previsto, "faltando": faltando}
            for c, faltando in pares
        ])  # fmt: skip
