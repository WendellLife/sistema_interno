from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ChamadoExternoView,
    EstoqueExternoView,
    EventosExternosView,
    ItemSyncView,
    NotaFiscalExternaView,
    SistemaExternoViewSet,
    SolicitacaoExternaView,
    WebhookViewSet,
)

router = DefaultRouter()
router.register("integracoes/sistemas", SistemaExternoViewSet, basename="sistema-externo")
router.register("integracoes/webhooks", WebhookViewSet, basename="webhook")

urlpatterns = [
    path("integracoes/solicitacoes/", SolicitacaoExternaView.as_view(), name="ext-solicitacao"),
    path("integracoes/chamados/", ChamadoExternoView.as_view(), name="ext-chamado"),
    path("integracoes/itens/sync/", ItemSyncView.as_view(), name="ext-itens-sync"),
    path("integracoes/notas-fiscais/", NotaFiscalExternaView.as_view(), name="ext-nota"),
    path("integracoes/estoque/", EstoqueExternoView.as_view(), name="ext-estoque"),
    path("integracoes/eventos/", EventosExternosView.as_view(), name="ext-eventos"),
    *router.urls,
]
