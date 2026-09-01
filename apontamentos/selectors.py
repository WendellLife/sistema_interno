"""Leitura/agregação de horas. Nada de agregação em @property de listagem."""

from __future__ import annotations

from django.db.models import Count, F, Q, Sum

from core import papeis
from core.permissions import papeis_de

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
    # `tipo` e `tipo_id` são campos do próprio Apontamento: usar os dois como apelido de
    # anotação faz o Django recusar a consulta. Agrega pelo caminho e renomeia depois.
    linhas = (
        qs.values("tipo_id", "tipo__nome", "tipo__ordem")
        .annotate(minutos=Sum("minutos"), apontamentos=Count("id"))
        .order_by("tipo__ordem")
    )
    return [
        {
            "tipo_id": linha["tipo_id"],
            "tipo": linha["tipo__nome"],
            "ordem": linha["tipo__ordem"],
            "minutos": linha["minutos"],
            "apontamentos": linha["apontamentos"],
        }
        for linha in linhas
    ]


def horas_por_pessoa(qs):
    # O apelido da soma NÃO pode ser "minutos": ele passaria a sombrear a coluna, e o
    # segundo Sum("minutos") somaria a própria soma em vez do campo.
    linhas = (
        qs.values("usuario_id", "usuario__first_name", "usuario__last_name", "usuario__setor__sigla")
        .annotate(total_min=Sum("minutos"),
                  retrabalho_min=Sum("minutos", filter=Q(tipo__exige_causa=True)))
        .order_by("-total_min")
    )  # fmt: skip
    return [
        {
            "usuario_id": linha["usuario_id"],
            "nome": linha["usuario__first_name"],
            "sobrenome": linha["usuario__last_name"],
            "setor": linha["usuario__setor__sigla"],
            "minutos": linha["total_min"],
            "retrabalho_min": linha["retrabalho_min"] or 0,
        }
        for linha in linhas
    ]


def horas_por_chamado(qs):
    return list(
        qs.filter(chamado__isnull=False)
        .values("chamado_id", numero=F("chamado__numero"), titulo=F("chamado__titulo"),
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


def pendentes_para(aprovador, qs=None):
    """Fila de aprovação que `aprovador` enxerga — a MESMA regra do serviço `pode_aprovar`.

    Gerente de setor vê o próprio setor; Gerente de TI e Administrador veem tudo. Existe
    como selector para a tela e a API não terem duas implementações do mesmo escopo.
    """
    qs = base_listagem() if qs is None else qs
    qs = qs.filter(pendente_aprovacao=True, recusado_em__isnull=True).order_by("inicio")
    meus = papeis_de(aprovador)
    if meus & {papeis.GERENTE_TI, papeis.ADMINISTRADOR}:
        return qs
    if papeis.GERENTE_SETOR in meus:
        return qs.filter(usuario__setor=aprovador.setor)
    return qs.none()
