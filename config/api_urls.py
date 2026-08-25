from django.urls import include, path

urlpatterns = [
    path("auth/", include("core.urls")),
    path("", include("chamados.urls")),
]
