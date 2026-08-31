"""Agregações do painel e do relatório de SLA."""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from chamados.models import STATUS_ABERTOS, Chamado
from core.calendario import dia_util, feriados_do_sistema
from core.models import User


def mes_corrente() -> tuple[date, date]:
    hoje = timezone.localdate()
    inicio = hoje.replace(day=1)
    fim = (inicio + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return inicio, fim


def dias_uteis(de: date, ate: date) -> int:
    feriados = feriados_do_sistema(de.year) | feriados_do_sistema(ate.year)
    d, n = de, 0
    while d <= ate:
        n += dia_util(d, feriados)
        d += timedelta(days=1)
    return n


def horas_previstas(de: date, ate: date, setor=None) -> float:
    """Capacidade: Σ capacidade diária das pessoas ativas para apontamento × dias úteis do período."""
    qs = User.objects.filter(is_active=True, ativo_para_apontamento=True)
    if setor:
        qs = qs.filter(setor=setor)
    else:
        qs = qs.filter(setor__sigla="TI")
    minutos_dia = sum(qs.values_list("capacidade_diaria_min", flat=True))
    return round(minutos_dia * dias_uteis(de, ate) / 60, 1)


def sla(de=None, ate=None, setor=None) -> dict:
    """Cumprimento por categoria e por prioridade sobre chamados entregues no período."""
    qs = Chamado.objects.filter(status=Chamado.Status.ENTREGUE, sla_cumprido__isnull=False)
    if de:
        qs = qs.filter(entregue_em__date__gte=de)
    if ate:
        qs = qs.filter(entregue_em__date__lte=ate)
    if setor:
        qs = qs.filter(setor_origem=setor)
    cumpridos = Count("id", filter=Q(sla_cumprido=True))

    def linhas(campo, rotulo):
        out = []
        for r in qs.values(campo).annotate(total=Count("id"), cumpridos=cumpridos).order_by(campo):
            out.append({rotulo: r[campo], "total": r["total"], "cumpridos": r["cumpridos"],
                        "percentual": round(100 * r["cumpridos"] / r["total"], 1) if r["total"] else 0.0})  # fmt: skip
        return out

    agg = qs.aggregate(total=Count("id"), cumpridos=cumpridos)
    return {
        "total": agg["total"],
        "cumpridos": agg["cumpridos"],
        "percentual": round(100 * agg["cumpridos"] / agg["total"], 1) if agg["total"] else 0.0,
        "vencidos_abertos": Chamado.objects.filter(status__in=STATUS_ABERTOS, sla_cumprido=False).count(),
        "por_categoria": linhas("categoria__nome", "categoria"),
        "por_prioridade": linhas("prioridade", "prioridade"),
    }


def painel(*, user, de=None, ate=None, setor=None) -> dict:
    """Payload completo do painel (API e tela web usam o mesmo). Nenhum número vem de outro lugar."""
    from django.db.models import F

    from almoxarifado import selectors as almox
    from almoxarifado.models import Estoque
    from apontamentos import selectors as ap
    from chamados import selectors as cham
    from chamados.serializers import ChamadoListSerializer
    from chamados.viewsets import ChamadoViewSet
    from documentacao import selectors as doc

    if not de or not ate:
        de, ate = mes_corrente()
    horas_qs = ap.validos(de, ate, setor=setor)
    por_tipo = ap.horas_por_tipo(horas_qs)
    retrab = ap.percentual_retrabalho(horas_qs)
    espera = sum(linha["minutos"] for linha in por_tipo if linha["tipo"] == "Espera de terceiro")
    sla_dados = sla(de, ate, setor=setor)
    abaixo = Estoque.objects.filter(saldo__lte=F("item__estoque_minimo"))
    if setor:
        abaixo = abaixo.filter(setor=setor)

    class _Req:  # escopo da central sem depender de um request DRF
        pass

    vs = ChamadoViewSet()
    req = _Req()
    req.user = user
    vs.request = req
    escopo_chamados = vs.get_queryset()
    ids_escopo = set(escopo_chamados.values_list("pk", flat=True))
    risco = [c for c in cham.em_risco_de_sla() if c.pk in ids_escopo]
    return {
        "periodo": {"de": de, "ate": ate},
        "kpis": {
            "horas_apontadas": round(retrab["total_min"] / 60, 1),
            "horas_previstas": horas_previstas(de, ate, setor=setor),
            "sla_percentual": sla_dados["percentual"],
            "sla_meta": 90,
            "retrabalho_percentual": retrab["percentual"],
            "retrabalho_meta": 8,
            "itens_abaixo_minimo": abaixo.count(),
            "setores_com_item_abaixo": abaixo.values("setor").distinct().count(),
        },
        "horas_por_tipo": por_tipo,
        "mini": {"cobertura_documentacao": doc.cobertura(setor=setor, de=de, ate=ate)["percentual"],
                 "retrabalho_horas": round(retrab["retrabalho_min"] / 60, 1),
                 "espera_terceiro_horas": round(espera / 60, 1)},  # fmt: skip
        "risco_sla": ChamadoListSerializer(risco, many=True).data,
        "risco_sla_objetos": risco,
        "retrabalho_por_motivo": ap.retrabalho_por_motivo(horas_qs)[:5],
        "consumo_por_setor": almox.consumo_por_setor(almox.consumo(de, ate, setor=setor))[:5],
        "documentacao_pendente": [
            {"id": c.id, "numero": c.numero, "titulo": c.titulo, "setor": c.setor_origem.sigla,
             "responsavel": c.responsavel.nome if c.responsavel else None, "faltando": faltando,
             "sla_previsto": c.sla_previsto}
            for c, faltando in doc.documentacao_pendente(escopo_chamados)
        ],
    }
