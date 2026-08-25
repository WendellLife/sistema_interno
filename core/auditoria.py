"""Ponto único de escrita em `core.Auditoria`."""

from __future__ import annotations

from typing import Any

from django.db import models

from .models import Auditoria


def registrar(
    *,
    usuario,
    acao: str,
    objeto: models.Model,
    antes: dict[str, Any] | None = None,
    depois: dict[str, Any] | None = None,
) -> Auditoria:
    registro = Auditoria.objects.create(
        usuario=usuario,
        acao=acao,
        objeto_tipo=objeto._meta.label_lower,
        objeto_id=str(objeto.pk),
        antes=antes,
        depois=depois,
    )
    # Outbox de integração: toda ação auditada é um evento publicável (ver integracoes.eventos)
    from integracoes.eventos import publicar

    publicar(registro)
    return registro
