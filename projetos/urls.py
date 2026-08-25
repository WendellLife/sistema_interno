from rest_framework.routers import DefaultRouter

from .viewsets import ProjetoViewSet

router = DefaultRouter()
router.register("projetos", ProjetoViewSet, basename="projeto")
urlpatterns = router.urls
