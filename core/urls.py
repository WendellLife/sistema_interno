from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import CentroCustoViewSet, MeView, PermissaoModuloViewSet, SetorViewSet

router = DefaultRouter()
router.register("setores", SetorViewSet, basename="setor")
router.register("centros-custo", CentroCustoViewSet, basename="centro-custo")
router.register("permissoes", PermissaoModuloViewSet, basename="permissao")

urlpatterns = [
    path("auth/token/", TokenObtainPairView.as_view(), name="token"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", MeView.as_view(), name="me"),
    *router.urls,
]
