"""Compras: visão dos setores, fila de reposição, consumo sem OS e cotações."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from almoxarifado import selectors as almox_sel
from almoxarifado import services as almox
from almoxarifado.models import (
    AlertaReposicao,
    Cotacao,
    Estoque,
    Item,
    PropostaCotacao,
    Solicitacao,
)
from core.exceptions import RegraDeNegocio
from core.models import CentroCusto, Setor
from relatorios.selectors import mes_corrente

from .views import _exige_modulo, _modal_erro


def _pode_editar(request) -> bool:
    from core.permissions import nivel_no_modulo

    return nivel_no_modulo(request.user, "compras") == "E"


@login_required
def compras(request):
    _exige_modulo(request, "compras")
    de, ate = mes_corrente()
    consumo = almox_sel.consumo(de, ate)
    por_setor = {linha["setor_id"]: linha for linha in almox_sel.consumo_por_setor(consumo)}
    mais_consumido = {}
    for r in consumo.values("setor_id", "item__descricao").annotate(n=Count("id")).order_by("setor_id", "-n"):
        mais_consumido.setdefault(r["setor_id"], r["item__descricao"])
    linhas = []
    for s in Setor.objects.filter(ativo=True).order_by("nome"):
        est = Estoque.objects.filter(setor=s)
        rupturas = est.filter(saldo__lte=0).count()
        abaixo = est.filter(saldo__lte=F("item__estoque_minimo")).count()
        acao = ("chip-danger", "Comprar hoje") if rupturas else ("chip-warn", "Cotar") if abaixo else ("chip-ok", "Normal")
        cc = CentroCusto.objects.filter(setor=s, ativo=True).first()
        linhas.append({"s": s, "cc": cc, "consumo": (por_setor.get(s.id) or {}).get("valor") or 0, "abaixo": abaixo,
                       "rupturas": rupturas, "mais": mais_consumido.get(s.id, "—"), "acao": acao})  # fmt: skip
    ctx = {
        "linhas": linhas, "periodo": (de, ate),
        "kpis": {
            "rupturas": Estoque.objects.filter(saldo__lte=0).count(),
            "solicitacoes": Solicitacao.objects.filter(status="aberta").count(),
            "consumo_mes": sum(float(linha["consumo"]) for linha in linhas),
            "cotacoes": Cotacao.objects.exclude(status="fechada").count(),
        },
        "fila": AlertaReposicao.objects.filter(resolvido_em__isnull=True).select_related("item", "setor").order_by("criado_em")[:30],
        "sem_os": almox_sel.consumo(de, ate, sem_os=True).order_by("-criado_em")[:20],
        "cotacoes": Cotacao.objects.exclude(status="fechada").select_related("item").prefetch_related("propostas").order_by("prazo_resposta"),
        "pode_editar": _pode_editar(request), "itens": Item.objects.filter(ativo=True).order_by("codigo"),
        "hoje": timezone.localdate(),
    }
    return render(request, "web/compras/tela.html", ctx)


def _refresh():
    r = HttpResponse(status=204)
    r["HX-Refresh"] = "true"
    return r


@login_required
@require_POST
def abrir_cotacao(request):
    _exige_modulo(request, "compras", "E")
    try:
        almox.abrir_cotacao(item=get_object_or_404(Item, pk=request.POST.get("item")), quantidade=request.POST.get("quantidade") or 0,
                            prazo_resposta=parse_date(request.POST.get("prazo_resposta") or "") or date.today(), usuario=request.user)  # fmt: skip
    except RegraDeNegocio as e:
        return _modal_erro(request, e, status=e.status_http)
    return _refresh()


@login_required
@require_POST
def proposta(request, pk):
    _exige_modulo(request, "compras", "E")
    cot = get_object_or_404(Cotacao, pk=pk)
    try:
        almox.registrar_proposta(cotacao=cot, fornecedor=request.POST.get("fornecedor", ""), valor_unitario=request.POST.get("valor_unitario") or 0,
                                 prazo_entrega_dias=int(request.POST.get("prazo_entrega_dias") or 0), usuario=request.user)  # fmt: skip
    except RegraDeNegocio as e:
        return _modal_erro(request, e, status=e.status_http)
    return _refresh()


@login_required
@require_POST
def escolher(request, pk):
    _exige_modulo(request, "compras", "E")
    try:
        almox.escolher_proposta(proposta=get_object_or_404(PropostaCotacao, pk=pk), usuario=request.user)
    except RegraDeNegocio as e:
        return _modal_erro(request, e, status=e.status_http)
    return _refresh()


@login_required
@require_POST
def resolver_alerta(request, pk):
    _exige_modulo(request, "compras", "E")
    a = get_object_or_404(AlertaReposicao, pk=pk)
    a.resolvido_em = timezone.now()
    a.save(update_fields=["resolvido_em"])
    return _refresh()
