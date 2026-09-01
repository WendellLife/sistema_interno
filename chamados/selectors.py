"""Consultas de leitura/agregação de chamados."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from core import papeis
from core.calendario import feriados_do_sistema, minutos_uteis_entre
from core.permissions import papeis_de, ve_todos_setores

from .models import STATUS_ABERTOS, Chamado

LIMITE_RISCO_SLA_MIN = 8 * 60


def base_listagem():
    """Queryset com joins necessários para as 8 colunas da Central de tarefas."""
    return Chamado.objects.select_related(
        "setor_origem", "solicitante", "categoria", "responsavel", "projeto"
    )


def abertos():
    return base_listagem().filter(status__in=STATUS_ABERTOS)


def minutos_uteis_restantes(chamado: Chamado) -> int | None:
    if not chamado.sla_previsto or not chamado.aberto:
        return None
    agora = timezone.now()
    if chamado.sla_previsto <= agora:
        return 0
    feriados = feriados_do_sistema(agora.year)
    return minutos_uteis_entre(agora, chamado.sla_previsto, feriados)


def em_risco_de_sla():
    """Abertos com vencimento em < 8h úteis (aproximado por janela de 3 dias corridos,
    depois refinado em Python — o volume de abertos é pequeno)."""
    agora = timezone.now()
    candidatos = abertos().filter(sla_previsto__lte=agora + timedelta(days=3)).order_by("sla_previsto")
    return [c for c in candidatos if (minutos_uteis_restantes(c) or 0) < LIMITE_RISCO_SLA_MIN]


def resumo_central(qs) -> dict:
    total = qs.filter(status__in=STATUS_ABERTOS).count()
    vencidos = qs.filter(status__in=STATUS_ABERTOS, sla_cumprido=False).count()
    return {"abertos": total, "sla_vencido": vencidos}


def contagem_por_status(qs) -> dict[str, int]:
    return {r["status"]: r["n"] for r in qs.values("status").annotate(n=Count("id"))}


def filtro_busca(texto: str) -> Q:
    return Q(titulo__icontains=texto) | Q(descricao__icontains=texto) | Q(numero__icontains=texto)


def escopo_do_usuario(user, qs=None):
    """Chamados que `user` enxerga — a MESMA regra que o ChamadoViewSet aplica.

    Existe como selector para que o painel possa reusá-la sem fabricar um request falso
    em volta do viewset. O viewset delega para cá: uma implementação, não duas.
    """
    qs = base_listagem() if qs is None else qs
    if ve_todos_setores(user):
        return qs
    if papeis_de(user) & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}:
        return qs.filter(setor_origem=user.setor)
    return qs.filter(Q(solicitante=user) | Q(responsavel=user))
