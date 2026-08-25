"""Leitura/agregação de horas. Nada de agregação em @property de listagem."""

from __future__ import annotations

from django.db.models import Count, F, Q, Sum

from .models import Apontamento


def base_listagem():
    return Apontamento.objects.select_related(
        "usuario", "usuario__setor", "tipo", "chamado", "projeto", "motivo_retrabalho", "aprovado_por"
    )


def validos(de=None, ate=None, setor=None, usuario=None):
    """Apontamentos que entram nos indicadores: fechados e não pendentes."""
    qs = Apontamento.objects.filter(fim__isnull=False, pendente_aprovacao=False, recusado_em__isnull=True)
    if de:
        qs = qs.filter(inicio__date__gte=de)
    if ate:
        qs = qs.filter(inicio__date__lte=ate)
    if setor:
        qs = qs.filter(usuario__setor=setor)
    if usuario:
        qs = qs.filter(usuario=usuario)
    return qs


def horas_por_tipo(qs):
    return list(
        qs.values(tipo_id=F("tipo__id"), tipo=F("tipo__nome"), ordem=F("tipo__ordem"))
        .annotate(minutos=Sum("minutos"), apontamentos=Count("id"))
        .order_by("ordem")
    )


def horas_por_pessoa(qs):
    return list(
        qs.values(usuario_id=F("usuario__id"), nome=F("usuario__first_name"),
                  sobrenome=F("usuario__last_name"), setor=F("usuario__setor__sigla"))
        .annotate(minutos=Sum("minutos"),
                  retrabalho_min=Sum("minutos", filter=Q(tipo__exige_causa=True)))
        .order_by("-minutos")
    )  # fmt: skip


def horas_por_chamado(qs):
    return list(
        qs.filter(chamado__isnull=False)
        .values(chamado_id=F("chamado__id"), numero=F("chamado__numero"), titulo=F("chamado__titulo"),
                previstas_min=F("chamado__horas_previstas_min"))
        .annotate(minutos=Sum("minutos"))
        .order_by("-minutos")
    )  # fmt: skip


def retrabalho_por_motivo(qs):
    """Relatório por MOTIVO, nunca por pessoa (07 — riscos)."""
    return list(
        qs.filter(tipo__exige_causa=True)
        .values(motivo_id=F("motivo_retrabalho__id"), motivo=F("motivo_retrabalho__nome"))
        .annotate(minutos=Sum("minutos"), apontamentos=Count("id"))
        .order_by("-minutos")
    )


def retrabalho_por_origem(qs):
    """Horas de retrabalho por setor de origem do chamado."""
    return list(
        qs.filter(tipo__exige_causa=True, chamado__isnull=False)
        .values(setor_id=F("chamado__setor_origem__id"), setor=F("chamado__setor_origem__sigla"))
        .annotate(minutos=Sum("minutos"))
        .order_by("-minutos")
    )


def percentual_retrabalho(qs) -> dict:
    agg = qs.aggregate(total=Sum("minutos"), retrabalho=Sum("minutos", filter=Q(tipo__exige_causa=True)))
    total = agg["total"] or 0
    retrabalho = agg["retrabalho"] or 0
    return {
        "total_min": total,
        "retrabalho_min": retrabalho,
        "percentual": round(100 * retrabalho / total, 1) if total else 0.0,
    }
