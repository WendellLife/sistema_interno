from django.urls import path

from .views import BuscaView

urlpatterns = [path("busca/", BuscaView.as_view(), name="busca")]
