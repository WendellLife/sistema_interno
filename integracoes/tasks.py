import hashlib
import hmac
import json
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import EventoIntegracao

MAX_TENTATIVAS = 8


def assinar(segredo: str, corpo: bytes) -> str:
    return hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


@shared_task(name="integracoes.entregar_evento")
def entregar_evento(evento_id: int) -> str:
    """POST do evento na URL do webhook com HMAC. Backoff exponencial até MAX_TENTATIVAS."""
    import requests

    ev = EventoIntegracao.objects.select_related("webhook").get(pk=evento_id)
    if ev.status == EventoIntegracao.Status.ENTREGUE:
        return "ja_entregue"
    corpo = json.dumps(ev.carga, ensure_ascii=False).encode()
    try:
        r = requests.post(
            ev.webhook.url, data=corpo, timeout=10,
            headers={"Content-Type": "application/json", "X-Evento": ev.acao, "X-Evento-Id": str(ev.pk),
                     "X-Assinatura": assinar(ev.webhook.segredo, corpo)},
        )  # fmt: skip
        r.raise_for_status()
        ev.status = EventoIntegracao.Status.ENTREGUE
        ev.entregue_em = timezone.now()
        ev.ultimo_erro = ""
    except Exception as e:  # noqa: BLE001
        ev.tentativas += 1
        ev.ultimo_erro = str(e)[:240]
        if ev.tentativas >= MAX_TENTATIVAS:
            ev.status = EventoIntegracao.Status.FALHOU
        else:
            ev.proxima_tentativa = timezone.now() + timedelta(minutes=2 ** ev.tentativas)
    ev.save()
    return ev.status


@shared_task(name="integracoes.reentregar_pendentes")
def reentregar_pendentes() -> int:
    agora = timezone.now()
    ids = list(
        EventoIntegracao.objects.filter(status="pendente", tentativas__gt=0, proxima_tentativa__lte=agora)
        .values_list("pk", flat=True)[:200]
    )
    for pk in ids:
        entregar_evento.delay(pk)
    return len(ids)
