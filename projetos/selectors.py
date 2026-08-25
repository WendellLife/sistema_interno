from __future__ import annotations

from django.db.models import Case, F, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import FASES_HISTORICO, FASES_KANBAN, Projeto


def base_listagem():
    """Horas realizadas anotadas (apontamentos fechados e não pendentes) + risco de prazo."""
    hoje = timezone.localdate()
    validos = Q(apontamentos__fim__isnull=False, apontamentos__pendente_aprovacao=False)
    return (
        Projeto.objects.select_related("setor_solicitante", "patrocinador", "responsavel")
        .prefetch_related("marcos", "alocacoes__usuario")
        .annotate(
            minutos_realizados=Coalesce(Sum("apontamentos__minutos", filter=validos), Value(0)),
            em_risco=Case(
                When(fase__in=FASES_KANBAN, fim_previsto__lt=hoje, then=Value(True)),
                default=Value(False),
            ),
        )
    )


def kanban(qs):
    return {fase: [p for p in qs if p.fase == fase] for fase in FASES_KANBAN}


def kpis(qs) -> dict:
    abertos = [p for p in qs if p.fase in FASES_KANBAN]
    return {
        "abertos": len(abertos),
        "em_desenvolvimento": sum(1 for p in abertos if p.fase == Projeto.Fase.DESENVOLVIMENTO),
        "em_risco": sum(1 for p in abertos if p.em_risco),
        "horas_previstas": sum(p.horas_estimadas for p in abertos),
        "horas_realizadas": round(sum(p.minutos_realizados for p in abertos) / 60, 1),
    }


def capacidade_alocada_por_pessoa():
    from core.models import User

    return (
        User.objects.filter(is_active=True)
        .annotate(alocado=Coalesce(
            Sum("alocacao__percentual", filter=Q(alocacao__projeto__fase__in=FASES_KANBAN)),
            Value(0), output_field=IntegerField(),
        ))  # fmt: skip
        .filter(alocado__gt=0)
        .values("id", "first_name", "last_name", "alocado")
        .order_by("-alocado")
    )


def historico(qs):
    return qs.filter(fase__in=FASES_HISTORICO).order_by(F("encerrado_em").desc(nulls_last=True))
