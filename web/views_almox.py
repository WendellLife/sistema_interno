"""Almoxarifado: tela do setor, 4 modais e leitura de QR. Regra fica em almoxarifado.services."""

from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from almoxarifado import selectors as almox_sel
from almoxarifado import services as almox
from almoxarifado.models import AlertaReposicao, Estoque, Inventario, Item, Movimento, Solicitacao
from core import papeis
from core.exceptions import RegraDeNegocio
from core.models import CentroCusto, Setor
from core.permissions import nivel_no_modulo, papeis_de, ve_todos_setores

from .views import _exige_modulo, _modal_erro, _setores


def _setor_da_tela(request) -> Setor:
    if ve_todos_setores(request.user) and request.GET.get("setor"):
        return get_object_or_404(Setor, pk=request.GET["setor"], ativo=True)
    return request.user.setor


def _pode_escrever(request) -> bool:
    return nivel_no_modulo(request.user, "almoxarifado") == "E"


def _pode_compras(request, setor) -> bool:
    meus = papeis_de(request.user)
    if meus & {papeis.COMPRAS, papeis.ADMINISTRADOR}:
        return True
    return papeis.RESPONSAVEL in meus and setor.pk == request.user.setor_id


def _situacao(saldo, minimo) -> tuple[str, str]:
    if saldo <= 0:
        return "chip-danger", "Ruptura"
    if saldo <= minimo:
        return "chip-warn", "Abaixo do mínimo"
    return "chip-ok", "OK"


def _ctx_estoque(request, setor):
    linhas = []
    for e in almox_sel.estoque_por_setor(setor):
        cls, rot = _situacao(e.saldo, e.item.estoque_minimo)
        linhas.append({"e": e, "cls": cls, "rotulo": rot})
    return {"estoque": linhas}


def _ctx_movimentos(setor):
    hoje = timezone.localdate()
    return {"movimentos": Movimento.objects.filter(setor=setor, criado_em__date=hoje).select_related("item", "usuario").order_by("-criado_em")[:30]}


def _ctx_solicitacoes(request, setor):
    qs = Solicitacao.objects.filter(setor=setor).select_related("solicitante").prefetch_related("itens__item").order_by("-criado_em")
    if not (ve_todos_setores(request.user) or papeis_de(request.user) & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}):
        qs = qs.filter(solicitante=request.user)
    meus = papeis_de(request.user)
    return {
        "solicitacoes": qs[:20],
        "pode_aprovar": bool(meus & {papeis.GERENTE_SETOR, papeis.ADMINISTRADOR}) and (papeis.ADMINISTRADOR in meus or setor.pk == request.user.setor_id),
        "pode_atender": _pode_escrever(request) and (ve_todos_setores(request.user) or setor.pk == request.user.setor_id),
    }


@login_required
def almoxarifado(request):
    _exige_modulo(request, "almoxarifado")
    setor = _setor_da_tela(request)
    estoques = Estoque.objects.filter(setor=setor).select_related("item")
    cc = CentroCusto.objects.filter(setor=setor, ativo=True).first()
    ctx = {
        "setor": setor, "setores": _setores(request.user), "cc": cc,
        "ccs": CentroCusto.objects.filter(setor=setor, ativo=True),
        "outros_setores": Setor.objects.filter(ativo=True).exclude(pk=setor.pk),
        "kpis": {
            "itens": estoques.count(),
            "abaixo": estoques.filter(saldo__lte=F("item__estoque_minimo"), saldo__gt=0).count(),
            "rupturas": estoques.filter(saldo__lte=0).count(),
            "solicitacoes_abertas": Solicitacao.objects.filter(setor=setor, status="aberta").count(),
            "alertas": AlertaReposicao.objects.filter(setor=setor, resolvido_em__isnull=True).count(),
        },
        "pode_escrever": _pode_escrever(request) and (ve_todos_setores(request.user) or setor.pk == request.user.setor_id),
        "pode_compras": _pode_compras(request, setor),
        "inventario_aberto": Inventario.objects.filter(setor=setor, status="aberto").first(),
        "hoje": timezone.localdate(),
        **_ctx_estoque(request, setor), **_ctx_movimentos(setor), **_ctx_solicitacoes(request, setor),
    }
    return render(request, "web/almox/tela.html", ctx)


@login_required
def itens_busca(request):
    """Autocomplete dos modais: código/descrição, com saldo do setor."""
    setor = _setor_da_tela(request)
    q = request.GET.get("q", "").strip()
    qs = Item.objects.filter(ativo=True)
    if q:
        qs = qs.filter(Q(codigo__icontains=q) | Q(descricao__icontains=q) | Q(codigo_sankhya__icontains=q))
    itens = []
    for i in qs.order_by("codigo")[:8]:
        itens.append({"i": i, "saldo": almox_sel.saldo(i, setor)})
    return render(request, "web/almox/_itens_busca.html", {"itens": itens, "alvo": request.GET.get("alvo", "")})


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v).replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _refresh():
    r = HttpResponse(status=204)
    r["HX-Refresh"] = "true"
    return r


@login_required
@require_POST
def solicitar(request):
    _exige_modulo(request, "almoxarifado", "E")
    setor = _setor_da_tela(request)
    cc = CentroCusto.objects.filter(pk=request.POST.get("centro_custo"), ativo=True).first()
    if not cc:
        return render(request, "web/partials/_modal_erro.html", {"erro": {"mensagem": "Centro de custo é obrigatório."}}, status=400)
    itens = []
    for item_id, qtd in zip(request.POST.getlist("item"), request.POST.getlist("quantidade"), strict=False):
        if item_id and _dec(qtd) > 0:
            itens.append({"item": get_object_or_404(Item, pk=item_id), "quantidade": _dec(qtd)})
    try:
        almox.criar_solicitacao(solicitante=request.user, centro_custo=cc, itens=itens, os_ref=request.POST.get("os_ref", ""),
                                urgente=bool(request.POST.get("urgente")), setor=setor)  # fmt: skip
    except RegraDeNegocio as e:
        return _modal_erro(request, e, status=e.status_http)
    return _refresh()


@login_required
@require_POST
def solicitacao_acao(request, pk, acao):
    # aprovar/negar é decisão de gerente (matriz "V" basta; o serviço confere o papel e o setor);
    # atender movimenta estoque e exige "E".
    _exige_modulo(request, "almoxarifado", "E" if acao == "atender" else "V")
    sol = get_object_or_404(Solicitacao, pk=pk)
    try:
        if acao == "aprovar":
            almox.aprovar_solicitacao(solicitacao=sol, aprovador=request.user)
        elif acao == "negar":
            motivo = request.POST.get("motivo") or request.headers.get("HX-Prompt") or "Negada"
            almox.negar_solicitacao(solicitacao=sol, aprovador=request.user, motivo=motivo)
        elif acao == "atender":
            almox.atender_solicitacao(solicitacao=sol, usuario=request.user)
        else:
            raise Http404
    except RegraDeNegocio as e:
        return _modal_erro(request, e, status=e.status_http)
    return _refresh()


@login_required
@require_POST
def saida_rapida(request):
    """Saída direta (QR / linha do estoque): exige referência — o serviço recusa sem ela."""
    _exige_modulo(request, "almoxarifado", "E")
    setor = _setor_da_tela(request)
    item = get_object_or_404(Item, pk=request.POST.get("item"))
    cc = CentroCusto.objects.filter(pk=request.POST.get("centro_custo") or 0).first()
    try:
        almox.registrar_movimento(item=item, setor=setor, tipo="saida", quantidade=_dec(request.POST.get("quantidade")),
                                  usuario=request.user, centro_custo=cc, os_ref=request.POST.get("os_ref", ""))  # fmt: skip
    except RegraDeNegocio as e:
        return _modal_erro(request, e, status=e.status_http)
    return _refresh()


@login_required
@require_POST
def transferir(request):
    _exige_modulo(request, "almoxarifado", "E")
    origem = _setor_da_tela(request)
    destino = get_object_or_404(Setor, pk=request.POST.get("setor_destino"))
    item = get_object_or_404(Item, pk=request.POST.get("item"))
    try:
        almox.transferir(item=item, setor_origem=origem, setor_destino=destino, quantidade=_dec(request.POST.get("quantidade")),
                         motivo=request.POST.get("motivo", ""), usuario=request.user)  # fmt: skip
    except RegraDeNegocio as e:
        return _modal_erro(request, e, status=e.status_http)
    return _refresh()


@login_required
def previa_transferencia(request):
    """Alerta âmbar ao vivo: 'A origem ficará abaixo do mínimo (5 UN)'."""
    setor = _setor_da_tela(request)
    item = Item.objects.filter(pk=request.GET.get("item") or 0).first()
    if not item:
        return HttpResponse("")
    saldo = almox_sel.saldo(item, setor)
    qtd = _dec(request.GET.get("quantidade"))
    avisos = [("muted", f"Saldo atual em {setor.sigla}: {saldo.normalize()} {item.unidade}")]
    if qtd > saldo:
        avisos.append(("danger", f"Só há {saldo.normalize()} {item.unidade} disponíveis."))
    elif qtd > 0 and saldo - qtd < item.estoque_minimo:
        avisos.append(("warn", f"A origem ficará abaixo do mínimo ({item.estoque_minimo.normalize()} {item.unidade}) — Compras será notificada."))
    return render(request, "web/tarefas/_avisos_manual.html", {"avisos": avisos})


@login_required
@require_POST
def entrada_nota(request):
    _exige_modulo(request, "almoxarifado", "E")
    setor = _setor_da_tela(request)
    if not _pode_compras(request, setor):
        raise Http404
    itens = []
    for item_id, pedida, recebida, custo, div in zip(
        request.POST.getlist("item"), request.POST.getlist("pedida"), request.POST.getlist("recebida"),
        request.POST.getlist("custo"), request.POST.getlist("divergencia"), strict=False,
    ):
        if item_id:
            itens.append({"item": get_object_or_404(Item, pk=item_id), "quantidade_pedida": _dec(pedida),
                          "quantidade_recebida": _dec(recebida), "custo_unitario": _dec(custo), "divergencia": div})  # fmt: skip
    try:
        nota = almox.entrada_por_nota(
            usuario=request.user, setor=setor, itens=itens, numero=request.POST.get("numero", ""), serie=request.POST.get("serie", ""),
            fornecedor=request.POST.get("fornecedor", ""), cnpj=request.POST.get("cnpj", ""),
            emissao=date.fromisoformat(request.POST.get("emissao") or str(timezone.localdate())),
            valor_total=_dec(request.POST.get("valor_total")),
        )  # fmt: skip
        if arquivo := request.FILES.get("arquivo"):
            nota.arquivo = arquivo
            nota.save(update_fields=["arquivo"])
    except RegraDeNegocio as e:
        return _modal_erro(request, e, status=e.status_http)
    return _refresh()


@login_required
def inventario(request):
    """GET: modal com 5 itens da rodada (aberto ou novo). POST: grava contagens e fecha."""
    _exige_modulo(request, "almoxarifado", "E")
    setor = _setor_da_tela(request)
    if not _pode_compras(request, setor):
        raise Http404
    inv = Inventario.objects.filter(setor=setor, status="aberto").first()
    if request.method == "POST":
        if not inv:
            raise Http404
        contagens = {}
        for item_id, contado in zip(request.POST.getlist("item"), request.POST.getlist("contado"), strict=False):
            if contado.strip() != "":
                contagens[int(item_id)] = _dec(contado)
        try:
            almox.registrar_contagens(inventario=inv, contagens=contagens, usuario=request.user)
            if request.POST.get("acao") == "fechar":
                inv = almox.fechar_inventario(inventario=inv, usuario=request.user)
                return render(request, "web/almox/_modal_inventario_fechado.html", {"inv": inv, "setor": setor})
        except RegraDeNegocio as e:
            return _modal_erro(request, e, status=e.status_http)
        return _refresh()
    if not inv:
        # rodada: os 5 itens do setor contados há mais tempo (ou nunca)
        candidatos = list(Estoque.objects.filter(setor=setor).select_related("item").order_by("atualizado_em")[:5])
        inv = almox.abrir_inventario(setor=setor, responsavel=request.user, itens=[e.item for e in candidatos])
    contagens = inv.contagens.select_related("item").order_by("item__codigo")
    return render(request, "web/almox/_modal_inventario.html", {"inv": inv, "setor": setor, "contagens": contagens})


@login_required
def qrcode(request, codigo=None):
    _exige_modulo(request, "almoxarifado")
    setor = _setor_da_tela(request)
    codigo = codigo or request.GET.get("codigo", "").strip()
    item = Item.objects.filter(codigo=codigo, ativo=True).select_related("setor_dono").first() if codigo else None
    saldo = almox_sel.saldo(item, setor) if item else None
    ctx = {"setor": setor, "codigo": codigo, "item": item, "saldo": saldo,
           "ccs": CentroCusto.objects.filter(setor=setor, ativo=True), "pode_escrever": _pode_escrever(request)}  # fmt: skip
    if item:
        ctx["cls"], ctx["rotulo"] = _situacao(saldo, item.estoque_minimo)
    if request.headers.get("HX-Request"):
        return render(request, "web/almox/_qr_resultado.html", ctx)
    return render(request, "web/almox/qrcode.html", ctx)
