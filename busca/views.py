from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .services import buscar


class BuscaView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "busca"

    def get(self, request):
        return Response({"resultados": buscar(user=request.user, q=request.query_params.get("q", ""))})
