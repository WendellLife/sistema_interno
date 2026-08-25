from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CentroCusto, PermissaoModulo, Setor
from .permissions import EhAdministrador, invalidar_matriz
from .serializers import (
    CentroCustoSerializer,
    PermissaoModuloSerializer,
    SetorSerializer,
    montar_me,
)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(montar_me(request.user))


class SetorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Setor.objects.filter(ativo=True)
    serializer_class = SetorSerializer
    pagination_class = None


class CentroCustoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CentroCusto.objects.filter(ativo=True).select_related("setor")
    serializer_class = CentroCustoSerializer
    filterset_fields = ["setor"]
    pagination_class = None


class PermissaoModuloViewSet(viewsets.ModelViewSet):
    """Tela 'SLA e permissões' (Admin). A matriz é dado editável."""

    queryset = PermissaoModulo.objects.all().order_by("modulo", "papel")
    serializer_class = PermissaoModuloSerializer
    permission_classes = [IsAuthenticated, EhAdministrador]
    pagination_class = None
    http_method_names = ["get", "put", "patch", "head", "options"]

    def perform_update(self, serializer):
        from .auditoria import registrar

        antes = {"nivel": serializer.instance.nivel}
        obj = serializer.save()
        registrar(
            usuario=self.request.user,
            acao="permissao.alterar",
            objeto=obj,
            antes=antes,
            depois={"nivel": obj.nivel},
        )
        invalidar_matriz()
