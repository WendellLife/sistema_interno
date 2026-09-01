"""Exceções de regra de negócio e tradução para respostas HTTP estruturadas."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


class RegraDeNegocio(Exception):
    """Base. `codigo` vira `erro` no JSON; `status_http` padrão 409."""

    # Anotados: sem o tipo explícito o mypy infere Literal[409] / Literal["..."] da base
    # e recusa toda subclasse que usa outro código — que é o caso normal aqui.
    codigo: str = "regra_de_negocio"
    status_http: int = status.HTTP_409_CONFLICT

    def __init__(self, mensagem: str, **extras: Any):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.extras = extras

    def como_dict(self) -> dict[str, Any]:
        return {"erro": self.codigo, "mensagem": self.mensagem, **self.extras}


class ValidacaoDeCampo(RegraDeNegocio):
    """Erro 400 no formato DRF `{campo: [mensagem]}`."""

    codigo = "validacao"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self, campo: str, mensagem: str):
        super().__init__(mensagem)
        self.campo = campo

    def como_dict(self) -> dict[str, Any]:
        return {self.campo: [self.mensagem]}


def tratar_excecao(exc, context):
    if isinstance(exc, RegraDeNegocio):
        return Response(exc.como_dict(), status=exc.status_http)
    return exception_handler(exc, context)
