"""Views server-rendered. Regra continua nos services; aqui só há leitura, formulário e partial."""

from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apontamentos import selectors as ap_sel
from apontamentos import services as ap_services
from apontamentos.models import Apontamento, MotivoRetrabalho, TipoTrabalho
from chamados import selectors as cham_sel
from chamados import services as cham_services
from chamados.filters import ChamadoFilter
from chamados.models import STATUS_ABERTOS, Categoria, Chamado, RegraSLA
from core import papeis
from core.calendario import FUSO
from core.exceptions import RegraDeNegocio
from core.permissions import eh_ti, nivel_no_modulo, papeis_de, ve_todos_setores
from documentacao import selectors as doc_sel
from documentacao import services as doc_services
from documentacao.models import Documento

from .forms import ComentarioForm, LancamentoManualForm, NovoChamadoForm


class Entrar(LoginView):
    template_name = "web/login.html"
    redirect_authenticated_user = True


class Sair(LogoutView):
    next_page = "web:entrar"


# ---------------------------------------------------------------- escopo (mesmo critério da API)


def _chamados_escopo(user):
    from django.db.models import Sum, Value
    from django.db.models.functions import Coalesce

    validos = Q(apontamentos__fim__isnull=False, apontamentos__pendente_aprovacao=False, apontamentos__recusado_em__isnull=True)
    qs = cham_sel.base_listagem().annotate(
        minutos_realizados=Coalesce(Sum("apontamentos__minutos", filter=validos), Value(0))
    )
    if ve_todos_setores(user):
        return qs
    if papeis_de(user) & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}:
        return qs.filter(setor_origem=user.setor)
    return qs.filter(Q(solicitante=user) | Q(responsavel=user))


def _chamado_ou_404(request, pk) -> Chamado:
    c = _chamados_escopo(request.user).filter(pk=pk).first()
    if not c:
        raise Http404
    return c


def _exige_modulo(request, modulo, nivel="V"):
    n = nivel_no_modulo(request.user, modulo)
    if n == "-" or (nivel == "E" and n != "E"):
        raise Http404


# ---------------------------------------------------------------- central de tarefas


@login_required
def tarefas(request):
    _exige_modulo(request, "tarefas")
    params = request.GET.copy()
    params.setdefault("status", "abertos")
    f = ChamadoFilter(params, queryset=_chamados_escopo(request.user))
    qs = f.qs.order_by("sla_previsto", "-criado_em")
    pagina = Paginator(qs, 50).get_page(request.GET.get("pagina"))
    # 05 §2: a 8ª coluna é o chip de Documento. Uma consulta para a página toda.
    situacao_doc = doc_sel.situacao_por_chamado(pagina.object_list)
    for chamado in pagina.object_list:
        chamado.situacao_documento = situacao_doc.get(chamado.pk, "na")
    ctx = {
        "pagina": pagina,
        "filtros": params,
        "resumo": cham_sel.resumo_central(_chamados_escopo(request.user)),
        "em_risco": len(cham_sel.em_risco_de_sla()),
        "status_chips": [("abertos", "Abertos")] + [(s.value, s.label) for s in Chamado.Status],
        "prioridades": Chamado.Prioridade.choices,
        "categorias": Categoria.objects.all(),
        "responsaveis": _responsaveis(),
        "setores": _setores(request.user),
        "form_novo": NovoChamadoForm(),
        "sla_exemplos": _sla_exemplos(),
        "pode_abrir": nivel_no_modulo(request.user, "tarefas") == "E",
    }
    if request.headers.get("HX-Request"):
        return render(request, "web/tarefas/_tabela.html", ctx)
    return render(request, "web/tarefas/lista.html", ctx)


def _responsaveis():
    from core.models import User

    return User.objects.filter(is_active=True, setor__sigla="TI").order_by("first_name")


def _setores(user):
    from core.models import Setor

    return Setor.objects.filter(ativo=True) if ve_todos_setores(user) else []


def _sla_exemplos():
    base = {p: h for p, h in RegraSLA.objects.values_list("prioridade", "horas_uteis")}
    from chamados.models import SLA_PADRAO_HORAS

    return {p: base.get(p, h) for p, h in SLA_PADRAO_HORAS.items()}


@login_required
@require_POST
def abrir_chamado(request):
    _exige_modulo(request, "tarefas", "E")
    form = NovoChamadoForm(request.POST)
    if not form.is_valid():
        return render(request, "web/partials/_form_erros.html", {"form": form}, status=400)
    c = cham_services.abrir_chamado(solicitante=request.user, **form.cleaned_data)
    for arquivo in request.FILES.getlist("anexos"):
        cham_services.anexar(chamado=c, usuario=request.user, arquivo=arquivo)
    resp = HttpResponse(status=204)
    resp["HX-Redirect"] = reverse("web:tarefa", args=[c.pk])
    return resp


# ---------------------------------------------------------------- tarefa


@login_required
def tarefa_atual(request):
    """'Tarefa em andamento' do menu: o chamado do cronômetro ativo, senão o mais urgente atribuído."""
    ativo = ap_services.cronometro_aberto(request.user)
    if ativo and ativo.chamado_id:
        return redirect("web:tarefa", pk=ativo.chamado_id)
    c = _chamados_escopo(request.user).filter(status__in=STATUS_ABERTOS).filter(
        Q(responsavel=request.user) | Q(solicitante=request.user)
    ).order_by("sla_previsto").first()
    if c:
        return redirect("web:tarefa", pk=c.pk)
    return redirect("web:tarefas")


def _ctx_apontamento(request, chamado):
    tipos = list(TipoTrabalho.objects.all())
    validos = ap_sel.validos(usuario=request.user).filter(chamado=chamado)
    por_tipo = {linha["tipo_id"]: linha["minutos"] for linha in ap_sel.horas_por_tipo(validos)}
    ativo = ap_services.cronometro_aberto(request.user)
    linhas = []
    for t in tipos:
        minutos = por_tipo.get(t.id, 0)
        rodando = ativo is not None and ativo.tipo_id == t.id and ativo.chamado_id == chamado.id
        linhas.append({"tipo": t, "minutos": minutos, "ativo": rodando})
    maximo = max([linha["minutos"] for linha in linhas] + [1])
    total = sum(linha["minutos"] for linha in linhas)
    return {"linhas": linhas, "maximo": maximo, "total_min": total, "ativo": ativo,
            "ativo_neste": ativo is not None and ativo.chamado_id == chamado.id,
            "motivos": MotivoRetrabalho.objects.all(),
            "pendentes": Apontamento.objects.filter(usuario=request.user, chamado=chamado, pendente_aprovacao=True).count(),
            "fila_aprovacao": ap_sel.pendentes_para(request.user).count() if _pode_aprovar_horas(request.user) else 0}  # fmt: skip


def _ctx_documentacao(chamado):
    docs = doc_sel.base_listagem().filter(chamado=chamado).order_by("id")
    ok, faltando = cham_services.pode_entregar(chamado)
    return {"documentos": [(d, doc_sel.status_documento(d)) for d in docs], "pode_entregar": ok, "faltando": faltando}


def _ctx_tarefa(request, chamado):
    comentarios = chamado.comentarios.select_related("autor")
    if not eh_ti(request.user):
        comentarios = comentarios.filter(interno=False)
    proximos = sorted(cham_services.TRANSICOES.get(chamado.status, set()) - {Chamado.Status.ENTREGUE})
    return {
        "c": chamado,
        "comentarios": comentarios,
        "historico": chamado.historico.select_related("usuario").order_by("-quando")[:50],
        "anexos": chamado.anexos.all(),
        "proximos": [(s, Chamado.Status(s).label) for s in proximos],
        "pode_entregar_status": Chamado.Status.ENTREGUE in cham_services.TRANSICOES.get(chamado.status, set()),
        "pode_cancelar": bool(papeis_de(request.user) & cham_services.PAPEIS_PODEM_CANCELAR) and chamado.aberto,
        "eh_ti": eh_ti(request.user),
        "pode_editar": nivel_no_modulo(request.user, "tarefa") == "E",
        "hoje": timezone.localdate(),
        **_ctx_apontamento(request, chamado),
        **_ctx_documentacao(chamado),
    }


@login_required
def tarefa(request, pk):
    _exige_modulo(request, "tarefa")
    chamado = _chamado_ou_404(request, pk)
    return render(request, "web/tarefas/detalhe.html", _ctx_tarefa(request, chamado))


def _partial_apontamento(request, chamado, extra=None, status=200):
    ctx = {"c": chamado, **_ctx_apontamento(request, chamado), **(extra or {})}
    return render(request, "web/tarefas/_apontamento.html", ctx, status=status)


def _modal_erro(request, exc: RegraDeNegocio, chamado=None, status=409):
    """Erros de regra viram modal com causa e caminho de correção — nunca toast genérico."""
    return render(request, "web/partials/_modal_erro.html", {"erro": exc.como_dict(), "c": chamado}, status=status)


# ---------------------------------------------------------------- aprovação de horas


def _pode_aprovar_horas(user) -> bool:
    return bool(papeis_de(user) & papeis.APROVA_HORAS)


@login_required
def aprovacoes(request):
    """Modal de aprovação de horas (05 §3).

    A regra §4 manda o lançamento acima da capacidade ficar pendente e fora dos
    indicadores; sem esta tela não havia como tirá-lo desse estado pela interface.
    """
    if not _pode_aprovar_horas(request.user):
        raise Http404
    return render(request, "web/tarefas/_modal_aprovacao.html",
                  {"pendentes": ap_sel.pendentes_para(request.user)})  # fmt: skip


@login_required
@require_POST
def decidir_aprovacoes(request):
    if not _pode_aprovar_horas(request.user):
        raise Http404
    ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
    aprovar = request.POST.get("acao") == "aprovar"
    motivo = request.POST.get("motivo", "").strip()
    contexto = {"pendentes": ap_sel.pendentes_para(request.user)}
    if not ids:
        contexto["erro"] = {"mensagem": "Selecione ao menos um lançamento."}
        return render(request, "web/tarefas/_modal_aprovacao.html", contexto, status=400)
    # O escopo decide o que existe: id fora da fila do aprovador não é erro de permissão,
    # é registro que não está lá.
    visiveis = set(ap_sel.pendentes_para(request.user).values_list("pk", flat=True))
    if not set(ids) <= visiveis:
        raise Http404
    try:
        resultado = ap_services.decidir_em_lote(
            ids=ids, aprovador=request.user, aprovar=aprovar, motivo=motivo
        )  # fmt: skip
    except RegraDeNegocio as e:
        contexto["erro"] = e.como_dict()
        contexto["pendentes"] = ap_sel.pendentes_para(request.user)
        return render(request, "web/tarefas/_modal_aprovacao.html", contexto, status=409)
    n = len(resultado["decididos"])
    contexto = {
        "pendentes": ap_sel.pendentes_para(request.user),
        "aviso": f"{n} lançamento{'s' if n > 1 else ''} {'aprovado' if aprovar else 'recusado'}{'s' if n > 1 else ''}.",
    }
    return render(request, "web/tarefas/_modal_aprovacao.html", contexto)


@login_required
@require_POST
def cronometro(request, pk):
    """Iniciar/parar a partir da linha do card. HTMX troca o card inteiro."""
    _exige_modulo(request, "tarefa", "E")
    chamado = _chamado_ou_404(request, pk)
    acao = request.POST.get("acao")
    try:
        if acao == "parar":
            ap = ap_services.parar_cronometro(usuario=request.user)
            aviso = f"{ap.tipo.nome} parado — {_h(ap.minutos)} registradas"
        else:
            tipo = get_object_or_404(TipoTrabalho, pk=request.POST.get("tipo"))
            motivo = MotivoRetrabalho.objects.filter(pk=request.POST.get("motivo_retrabalho") or 0).first()
            _, pausado = ap_services.iniciar_cronometro(
                usuario=request.user, tipo=tipo, chamado=chamado, motivo_retrabalho=motivo,
                detalhe_retrabalho=request.POST.get("detalhe_retrabalho", ""),
            )  # fmt: skip
            aviso = f"{pausado.tipo.nome} pausado — {_h(pausado.minutos)} registradas" if pausado else ""
    except RegraDeNegocio as e:
        return _partial_apontamento(request, chamado, {"erro": e.como_dict(), "tipo_erro": request.POST.get("tipo")}, status=400)
    return _partial_apontamento(request, chamado, {"aviso": aviso})


@login_required
@require_POST
def lancamento_manual(request, pk):
    _exige_modulo(request, "tarefa", "E")
    chamado = _chamado_ou_404(request, pk)
    form = LancamentoManualForm(request.POST)
    if not form.is_valid():
        return _partial_apontamento(request, chamado, {"erro": {"mensagem": "Preencha tipo, data, início e fim."}}, status=400)
    d = form.cleaned_data
    tipo = get_object_or_404(TipoTrabalho, pk=d["tipo"])
    motivo = MotivoRetrabalho.objects.filter(pk=d["motivo_retrabalho"] or 0).first()
    inicio = datetime.combine(d["data"], d["inicio"], tzinfo=FUSO)
    fim = datetime.combine(d["data"], d["fim"], tzinfo=FUSO)
    try:
        ap = ap_services.criar_apontamento(
            usuario=request.user, tipo=tipo, chamado=chamado, inicio=inicio, fim=fim, observacao=d["observacao"],
            motivo_retrabalho=motivo, detalhe_retrabalho=d["detalhe_retrabalho"] or "",
        )  # fmt: skip
    except RegraDeNegocio as e:
        return _partial_apontamento(request, chamado, {"erro": e.como_dict(), "reabrir_manual": True}, status=400)
    aviso = f"{_h(ap.minutos)} lançadas em {tipo.nome}"
    if ap.pendente_aprovacao:
        aviso += " — aguardando aprovação do gerente"
    return _partial_apontamento(request, chamado, {"aviso": aviso})


@login_required
def previa_manual(request, pk):
    """Avisos em tempo real do modal (conflito e capacidade), sem gravar nada."""
    chamado = _chamado_ou_404(request, pk)
    form = LancamentoManualForm(request.GET)
    if not form.is_valid():
        return HttpResponse("")
    d = form.cleaned_data
    inicio = datetime.combine(d["data"], d["inicio"], tzinfo=FUSO)
    fim = datetime.combine(d["data"], d["fim"], tzinfo=FUSO)
    avisos = []
    if fim <= inicio:
        avisos.append(("danger", "O fim precisa ser depois do início."))
    else:
        minutos = ap_services._minutos(inicio, fim)
        if conf := ap_services._conflitante(request.user, inicio, fim):
            ini = timezone.localtime(conf.inicio)
            fimc = timezone.localtime(conf.fim) if conf.fim else None
            avisos.append(("danger", f"Conflita com {conf.tipo.nome} {ini:%H:%M}–{fimc:%H:%M}" if fimc else f"Conflita com {conf.tipo.nome} em andamento"))
        motivo = ap_services.exige_aprovacao(request.user, inicio, minutos)
        if motivo == "capacidade":
            total = ap_services.minutos_do_dia(request.user, d["data"], so_aprovados=False) + minutos
            avisos.append(("warn", f"Total do dia: {_h(total)} — exigirá aprovação do gerente"))
        elif motivo == "retroativo":
            avisos.append(("warn", "Lançamento com mais de 7 dias — exigirá aprovação do gerente"))
        avisos.insert(0, ("muted", f"Duração: {_h(minutos)}"))
    return render(request, "web/tarefas/_avisos_manual.html", {"avisos": avisos, "c": chamado})


@login_required
@require_POST
def transicao(request, pk):
    _exige_modulo(request, "tarefa", "E")
    chamado = _chamado_ou_404(request, pk)
    para = request.POST.get("status")
    try:
        cham_services.transicionar(chamado=chamado, para=para, usuario=request.user, comentario=request.POST.get("comentario", ""))
    except RegraDeNegocio as e:
        if e.codigo == "documentacao_incompleta":
            return render(request, "web/tarefas/_modal_bloqueio.html",
                          {"c": chamado, "faltando": e.extras["faltando"], "documentos": _ctx_documentacao(chamado)["documentos"]}, status=409)  # fmt: skip
        return _modal_erro(request, e, chamado, status=e.status_http)
    resp = HttpResponse(status=204)
    resp["HX-Refresh"] = "true"
    return resp


@login_required
@require_POST
def comentar(request, pk):
    _exige_modulo(request, "tarefa", "E")
    chamado = _chamado_ou_404(request, pk)
    form = ComentarioForm(request.POST)
    if form.is_valid():
        cham_services.comentar(chamado=chamado, autor=request.user, texto=form.cleaned_data["texto"],
                               interno=form.cleaned_data["interno"] and eh_ti(request.user))  # fmt: skip
    comentarios = chamado.comentarios.select_related("autor")
    if not eh_ti(request.user):
        comentarios = comentarios.filter(interno=False)
    return render(request, "web/tarefas/_comentarios.html", {"c": chamado, "comentarios": comentarios, "eh_ti": eh_ti(request.user)})


@login_required
def editor_documento(request, pk, secao):
    """GET: editor da seção com versões. POST: salvar rascunho ou publicar."""
    _exige_modulo(request, "documentacao")
    chamado = _chamado_ou_404(request, pk)
    if secao not in Documento.Secao.values:
        raise Http404
    doc = doc_services.obter_documento(chamado=chamado, secao=secao, criado_por=request.user)
    if request.method == "POST":
        _exige_modulo(request, "documentacao", "E")
        try:
            versao = doc_services.criar_rascunho(documento=doc, conteudo=request.POST.get("conteudo", ""), autor=request.user)
            if request.POST.get("acao") == "publicar":
                doc_services.publicar_versao(versao=versao, usuario=request.user)
        except RegraDeNegocio as e:
            return _modal_erro(request, e, chamado, status=e.status_http)
        resp = HttpResponse(status=204)
        resp["HX-Refresh"] = "true"
        return resp
    doc = doc_sel.base_listagem().get(pk=doc.pk)
    ultima = doc.versoes.order_by("-numero").first()
    return render(request, "web/tarefas/_modal_editor.html", {
        "c": chamado, "doc": doc, "status": doc_sel.status_documento(doc), "versoes": doc.versoes.select_related("autor"),
        "conteudo": (doc.versao_atual.conteudo if doc.versao_atual_id else (ultima.conteudo if ultima else "")),
        "pode_editar": nivel_no_modulo(request.user, "documentacao") == "E",
    })  # fmt: skip


@login_required
def busca(request):
    from busca.services import buscar

    resultados = buscar(user=request.user, q=request.GET.get("q", ""))
    return render(request, "web/partials/_busca_resultados.html", {"resultados": resultados, "q": request.GET.get("q", "")})


@login_required
def cronometro_estado(request):
    """JSON leve para o Alpine recalcular o relógio (a verdade é do servidor)."""
    from django.http import JsonResponse

    ativo = ap_services.cronometro_aberto(request.user)
    return JsonResponse({
        "ativo": bool(ativo), "inicio": ativo.inicio.isoformat() if ativo else None,
        "agora": timezone.now().isoformat(), "tipo": ativo.tipo.nome if ativo else None,
        "chamado": ativo.chamado_id if ativo else None,
    })  # fmt: skip


@login_required
def painel(request):
    """Painel web usando a mesma agregação exposta pela API."""
    from core.models import Setor
    from relatorios.selectors import painel as dados_painel

    _exige_modulo(request, "painel")

    pode_ver_todos = ve_todos_setores(request.user)
    setores = Setor.objects.filter(ativo=True).order_by("nome") if pode_ver_todos else Setor.objects.none()
    if pode_ver_todos:
        setor = setores.filter(pk=request.GET.get("setor")).first() if request.GET.get("setor") else None
    else:
        setor = request.user.setor

    dados = dados_painel(
        user=request.user,
        de=parse_date(request.GET.get("de") or ""),
        ate=parse_date(request.GET.get("ate") or ""),
        setor=setor,
    )
    kpis = dados["kpis"]
    return render(request, "web/painel.html", {
        "d": dados,
        "k": kpis,
        "risco": dados.pop("risco_sla_objetos", []),
        "setor": setor,
        "setores": setores,
        "abaixo_meta_sla": kpis["sla_percentual"] < kpis["sla_meta"],
        "acima_meta_retrabalho": kpis["retrabalho_percentual"] > kpis["retrabalho_meta"],
        "maximo": max((linha["minutos"] for linha in dados["horas_por_tipo"]), default=1),
        "max_motivo": max((linha["minutos"] for linha in dados["retrabalho_por_motivo"]), default=1),
        "max_consumo": max((linha["valor"] for linha in dados["consumo_por_setor"]), default=1),
    })


def _h(minutos: int) -> str:
    h, r = divmod(int(minutos or 0), 60)
    return f"{h}h{r:02d}" if r else f"{h}h"
