from django.urls import path
from rest_framework.routers import DefaultRouter

from .viewsets import (
    AlertasView,
    CotacaoViewSet,
    EscolherPropostaView,
    EstoqueView,
    InventarioViewSet,
    ItemViewSet,
    MovimentoViewSet,
    NotaFiscalViewSet,
    QRCodeView,
    SolicitacaoViewSet,
    TransferenciaViewSet,
)

router = DefaultRouter()
router.register("almoxarifado/itens", ItemViewSet, basename="item")
router.register("almoxarifado/movimentos", MovimentoViewSet, basename="movimento")
router.register("almoxarifado/solicitacoes", SolicitacaoViewSet, basename="solicitacao")
router.register("almoxarifado/notas-fiscais", NotaFiscalViewSet, basename="nota-fiscal")
router.register("almoxarifado/transferencias", TransferenciaViewSet, basename="transferencia")
router.register("almoxarifado/inventarios", InventarioViewSet, basename="inventario")
router.register("almoxarifado/cotacoes", CotacaoViewSet, basename="cotacao")

urlpatterns = [
    path("almoxarifado/estoque/", EstoqueView.as_view(), name="estoque"),
    path("almoxarifado/propostas/<int:pk>/escolher/", EscolherPropostaView.as_view(), name="proposta-escolher"),
    path("almoxarifado/qrcode/<str:codigo>/", QRCodeView.as_view(), name="qrcode"),
    path("almoxarifado/alertas/", AlertasView.as_view(), name="alertas"),
    *router.urls,
]
