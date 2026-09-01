from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def horas(minutos) -> str:
    """72 → '1h12'; 0 → '0h'; None → '—'."""
    if minutos is None:
        return "—"
    m = int(minutos)
    h, r = divmod(m, 60)
    return f"{h}h{r:02d}" if r else f"{h}h"


@register.filter
def horas_dec(minutos) -> str:
    """90 → '1,5'."""
    return f"{(minutos or 0) / 60:.1f}".replace(".", ",").rstrip("0").rstrip(",") or "0"


@register.filter
def sla_texto(chamado) -> str:
    if not chamado.sla_previsto:
        return "—"
    if not chamado.aberto:
        return "cumprido" if chamado.sla_cumprido else "estourado"
    from chamados.selectors import minutos_uteis_restantes

    rest = minutos_uteis_restantes(chamado)
    if chamado.sla_previsto <= timezone.now():
        atraso = int((timezone.now() - chamado.sla_previsto).total_seconds() // 3600)
        return f"atrasado {atraso}h" if atraso else "vencendo"
    return f"em {horas(rest)}"


@register.filter
def sla_pct(chamado) -> int:
    """Percentual do SLA consumido (barra fina da tabela)."""
    if not chamado.sla_previsto or not chamado.aberto:
        return 100
    from chamados.selectors import minutos_uteis_restantes

    rest = minutos_uteis_restantes(chamado) or 0
    from chamados.services import horas_uteis_sla

    total = horas_uteis_sla(chamado.categoria, chamado.prioridade) * 60
    return max(0, min(100, round(100 * (total - rest) / total))) if total else 100


@register.filter
def sla_classe(chamado) -> str:
    if not chamado.aberto:
        return "ok" if chamado.sla_cumprido else "danger"
    if chamado.sla_previsto and chamado.sla_previsto <= timezone.now():
        return "danger"
    return "warn" if sla_pct(chamado) >= 75 else "ok"


@register.filter
def chip_prioridade(prioridade) -> str:
    return {"critica": "chip-danger", "alta": "chip-warn", "media": "chip-info", "baixa": "chip-neutral"}.get(prioridade, "chip-neutral")


@register.filter
def chip_status(status) -> str:
    return {"novo": "chip-info", "triagem": "chip-info", "fila": "chip-neutral", "execucao": "chip-teal",
            "testes": "chip-teal", "aguarda": "chip-warn", "entregue": "chip-ok", "cancelado": "chip-neutral"}.get(status, "chip-neutral")  # fmt: skip


@register.filter
def chip_documento(situacao) -> str:
    return {"ok": "chip-ok", "pendente": "chip-warn", "na": "chip-neutral"}.get(situacao, "chip-neutral")


@register.filter
def rotulo_documento(situacao) -> str:
    return {"ok": "OK", "pendente": "Pendente", "na": "N/A"}.get(situacao, "N/A")


@register.filter
def pct(valor, maximo) -> int:
    try:
        return round(100 * float(valor) / float(maximo)) if float(maximo) else 0
    except (TypeError, ValueError):
        return 0


@register.simple_tag
def query_sem(request, *chaves):
    q = request.GET.copy()
    for c in chaves:
        q.pop(c, None)
    return q.urlencode()


@register.filter
def get_item(d, chave):
    return d.get(chave) if isinstance(d, dict) else None
