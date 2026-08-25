from django.urls import path

from .views import (
    PainelView,
    RelatorioAuditoriaView,
    RelatorioConsumoView,
    RelatorioHorasView,
    RelatorioRetrabalhoView,
    RelatorioSLAView,
)

urlpatterns = [
    path("relatorios/painel/", PainelView.as_view(), name="relatorio-painel"),
    path("relatorios/horas/", RelatorioHorasView.as_view(), name="relatorio-horas"),
    path("relatorios/retrabalho/", RelatorioRetrabalhoView.as_view(), name="relatorio-retrabalho"),
    path("relatorios/consumo/", RelatorioConsumoView.as_view(), name="relatorio-consumo"),
    path("relatorios/sla/", RelatorioSLAView.as_view(), name="relatorio-sla"),
    path("relatorios/auditoria/", RelatorioAuditoriaView.as_view(), name="relatorio-auditoria"),
]
