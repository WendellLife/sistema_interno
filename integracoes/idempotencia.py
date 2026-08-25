"""Mixin: POSTs com `Idempotency-Key` devolvem a resposta gravada na primeira chamada."""

from django.db import IntegrityError, transaction

from .models import ChaveIdempotencia


class IdempotenteMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        resp = super().finalize_response(request, response, *args, **kwargs)
        chave = request.headers.get("Idempotency-Key")
        sistema = getattr(request, "sistema_externo", None)
        if request.method == "POST" and chave and sistema and getattr(resp, "data", None) is not None and not getattr(request, "_idem_replay", False):
            try:
                with transaction.atomic():
                    ChaveIdempotencia.objects.create(
                        sistema=sistema, chave=chave[:128], caminho=request.path, status_http=resp.status_code, resposta=resp.data
                    )
            except IntegrityError:
                pass
        return resp

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        chave = request.headers.get("Idempotency-Key")
        sistema = getattr(request, "sistema_externo", None)
        if request.method == "POST" and chave and sistema:
            gravada = ChaveIdempotencia.objects.filter(sistema=sistema, chave=chave[:128]).first()
            if gravada:
                request._idem_replay = True
                from rest_framework.response import Response

                raise _Replay(Response(gravada.resposta, status=gravada.status_http))

    def handle_exception(self, exc):
        if isinstance(exc, _Replay):
            resp = exc.resposta
            resp["Idempotent-Replayed"] = "true"
            return resp
        return super().handle_exception(exc)


class _Replay(Exception):
    def __init__(self, resposta):
        self.resposta = resposta
