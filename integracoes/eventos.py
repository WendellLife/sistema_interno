"""Publicação de eventos a partir da auditoria (outbox). Chamado por `core.auditoria.registrar`."""

from __future__ import annotations

from functools import partial

from django.db import transaction

from .models import EventoIntegracao, Webhook


def carga_de(auditoria) -> dict:
    return {
        "id": auditoria.pk,
        "quando": auditoria.quando.isoformat() if auditoria.quando else None,
        "acao": auditoria.acao,
        "objeto": {"tipo": auditoria.objeto_tipo, "id": auditoria.objeto_id},
        "usuario": auditoria.usuario_id,
        "antes": auditoria.antes,
        "depois": auditoria.depois,
    }


def publicar(auditoria) -> int:
    """Cria um EventoIntegracao por webhook assinante e agenda a entrega após o commit."""
    assinantes = [w for w in Webhook.objects.filter(ativo=True, sistema__ativo=True) if w.assina(auditoria.acao)]
    if not assinantes:
        return 0
    carga = carga_de(auditoria)
    eventos = EventoIntegracao.objects.bulk_create(
        EventoIntegracao(webhook=w, auditoria=auditoria, acao=auditoria.acao, carga=carga) for w in assinantes
    )
    from .tasks import entregar_evento

    for ev in eventos:
        # `partial` no lugar do lambda com argumento padrão: captura o pk do mesmo jeito
        # e é tipável.
        transaction.on_commit(partial(entregar_evento.delay, ev.pk))
    return len(eventos)
