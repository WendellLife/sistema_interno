"""Projetos de TI: kanban de 8 colunas, histórico e modal Novo projeto."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core import papeis
from core.exceptions import RegraDeNegocio
from core.models import Setor, User
from core.permissions import papeis_de, ve_todos_setores
from projetos import selectors as psel
from projetos import services as pserv
from projetos.models import FASES_HISTORICO, FASES_KANBAN, Projeto

from .views import _exige_modulo, _modal_erro, _setores


def _escopo(user):
    qs = psel.base_listagem()
    if ve_todos_setores(user):
        return qs
    if papeis_de(user) & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}:
        return qs.filter(setor_solicitante=user.setor)
    return qs.none()


def _pode_editar(request) -> bool:
    from core.permissions import nivel_no_modulo

    return nivel_no_modulo(request.user, "projetos") == "E"


@login_required
def projetos(request):
    _exige_modulo(request, "projetos")
    qs = _escopo(request.user)
    if request.GET.get("setor"):
        qs = qs.filter(setor_solicitante_id=request.GET["setor"])
    abertos = qs.filter(fase__in=FASES_KANBAN).order_by("fim_previsto", "nome")
    colunas = []
    for f, ps in psel.kanban(abertos).items():
        for p in ps:
            p.estourou = p.horas_estimadas and p.minutos_realizados > p.horas_estimadas * 60
            p.progresso = min(100, round(100 * p.minutos_realizados / (p.horas_estimadas * 60))) if p.horas_estimadas else 0
        colunas.append((f, Projeto.Fase(f).label, ps))
    ctx = {
        "kpis": psel.kpis(abertos), "colunas": colunas, "setores": _setores(request.user),
        "pode_editar": _pode_editar(request), "todos_setores": Setor.objects.filter(ativo=True),
        "usuarios": User.objects.filter(is_active=True).order_by("first_name"),
        "ti": User.objects.filter(is_active=True, setor__sigla="TI").order_by("first_name"),
        "fases": [(f, Projeto.Fase(f).label) for f in FASES_KANBAN],
    }
    return render(request, "web/projetos/kanban.html", ctx)


@login_required
def historico(request):
    _exige_modulo(request, "projetos")
    qs = _escopo(request.user).filter(fase__in=FASES_HISTORICO)
    ano = request.GET.get("ano") or str(date.today().year)
    if ano != "todos":
        qs = qs.filter(encerrado_em__year=ano)
    if request.GET.get("setor"):
        qs = qs.filter(setor_solicitante_id=request.GET["setor"])
    if request.GET.get("situacao") in FASES_HISTORICO:
        qs = qs.filter(fase=request.GET["situacao"])
    linhas = []
    desvios = []
    for p in psel.historico(qs):
        realizadas = p.minutos_realizados / 60
        desvio = (realizadas - p.horas_estimadas) / p.horas_estimadas * 100 if p.horas_estimadas else None
        if desvio is not None and p.fase == "concluido":
            desvios.append(desvio)
        linhas.append({"p": p, "realizadas": realizadas, "desvio": desvio})
    anos = sorted({d.year for d in Projeto.objects.filter(encerrado_em__isnull=False).values_list("encerrado_em", flat=True)}, reverse=True)
    ctx = {
        "linhas": linhas, "ano": ano, "anos": anos, "setores": _setores(request.user),
        "kpis": {"concluidos": sum(1 for linha in linhas if linha["p"].fase == "concluido"),
                 "cancelados": sum(1 for linha in linhas if linha["p"].fase == "cancelado"),
                 "desvio_medio": round(sum(desvios) / len(desvios)) if desvios else 0},  # fmt: skip
    }
    return render(request, "web/projetos/historico.html", ctx)


@login_required
@require_POST
def novo(request):
    _exige_modulo(request, "projetos", "E")
    d = request.POST
    try:
        pserv.criar_projeto(
            usuario=request.user, nome=d.get("nome", "").strip(), setor_solicitante=get_object_or_404(Setor, pk=d.get("setor_solicitante")),
            patrocinador=get_object_or_404(User, pk=d.get("patrocinador")),
            responsavel=User.objects.filter(pk=d.get("responsavel") or 0).first(),
            horas_estimadas=int(d.get("horas_estimadas") or 0),
            inicio_previsto=parse_date(d.get("inicio_previsto") or ""), fim_previsto=parse_date(d.get("fim_previsto") or ""),
            situacao_final="",
        )  # fmt: skip
    except RegraDeNegocio as e:
        return _modal_erro(request, e, status=e.status_http)
    r = HttpResponse(status=204)
    r["HX-Refresh"] = "true"
    return r


@login_required
@require_POST
def mover(request, pk):
    """Clique + select no card: `fase`; concluir/cancelar pedem data e situação (vêm do prompt do modal)."""
    _exige_modulo(request, "projetos", "E")
    p = _escopo(request.user).filter(pk=pk).first()
    if not p:
        raise Http404
    try:
        pserv.mover_fase(projeto=p, para=request.POST.get("fase"), usuario=request.user,
                         encerrado_em=parse_date(request.POST.get("encerrado_em") or ""), situacao_final=request.POST.get("situacao_final", ""))  # fmt: skip
    except RegraDeNegocio as e:
        if e.codigo == "encerramento_sem_data":
            return render(request, "web/projetos/_modal_encerrar.html", {"p": p, "fase": request.POST.get("fase")}, status=400)
        return _modal_erro(request, e, status=e.status_http)
    r = HttpResponse(status=204)
    r["HX-Refresh"] = "true"
    return r
