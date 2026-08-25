from rest_framework.routers import DefaultRouter

from .viewsets import CategoriaViewSet, ChamadoViewSet, RegraSLAViewSet

router = DefaultRouter()
router.register("chamados", ChamadoViewSet, basename="chamado")
router.register("categorias", CategoriaViewSet, basename="categoria")
router.register("regras-sla", RegraSLAViewSet, basename="regra-sla")

urlpatterns = router.urls
