from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from core.health import health

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
    path("api/v1/", include("chamados.urls")),
    path("api/v1/", include("apontamentos.urls")),
    path("api/v1/", include("relatorios.urls")),
    path("api/v1/", include("documentacao.urls")),
    path("api/v1/", include("busca.urls")),
    path("api/v1/", include("almoxarifado.urls")),
    path("api/v1/", include("projetos.urls")),
    path("api/v1/", include("integracoes.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("health/", health, name="health"),
    path("api/v1/", include("almoxarifado.urls")),
    path("api/v1/", include("projetos.urls")),
    path("api/v1/", include("integracoes.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("health/", health, name="health"),
    path("", include("django_prometheus.urls")),
    path("", include("web.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
