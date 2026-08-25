from django.urls import path
from rest_framework.routers import DefaultRouter

from .viewsets import (
    ApontamentoViewSet,
    CronometroView,
    IniciarCronometroView,
    MotivoRetrabalhoViewSet,
    PararCronometroView,
    TipoTrabalhoViewSet,
)

router = DefaultRouter()
router.register("apontamentos", ApontamentoViewSet, basename="apontamento")
router.register("tipos-trabalho", TipoTrabalhoViewSet, basename="tipo-trabalho")
router.register("motivos-retrabalho", MotivoRetrabalhoViewSet, basename="motivo-retrabalho")

urlpatterns = [
    path("cronometro/", CronometroView.as_view(), name="cronometro"),
    path("cronometro/iniciar/", IniciarCronometroView.as_view(), name="cronometro-iniciar"),
    path("cronometro/parar/", PararCronometroView.as_view(), name="cronometro-parar"),
    *router.urls,
]
