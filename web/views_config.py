"""SLA e permissões (Admin) + Histórico de mudanças (auditoria)."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apontamentos.models import MotivoRetrabalho, TipoTrabalho
from chamados.models import SLA_PADRAO_HORAS, STATUS_ABERTOS, Categoria, Chamado, RegraSLA
from core import papeis
from core.auditoria import registrar
from core.calendario import feriados_do_sistema, somar_horas_uteis
from core.models import Auditoria, CentroCusto, PermissaoModulo, Setor
from core.permissions import invalidar_matriz

from .views import _exige_modulo

EXEMPLOS = {"critica": "linha parada", "alta": "setor bloqueado", "media": "melhoria pedida", "baixa": "ajuste cosmético"}
PAPEIS_MATRIZ = [papeis.COLABORADOR, papeis.RESPONSAVEL, papeis.GERENTE_SETOR, papeis.GERENTE_TI, papeis.COMPRAS]
ROTULOS_MODULO = {"painel": "Painel", "tarefas": "Central de tarefas", "tarefa": "Tarefa", "documentacao": "Documentação",
                  "almoxarifado": "Almoxarifado", "compras": "Compras", "projetos": "Projetos", "config": "Configurações"}  # fmt: skip


def _horas_por_prioridade() -> dict:
    """Regra global por prioridade = valor mais comum entre as categorias (ou padrão)."""
    out = {}
    for p, padrao in SLA_PADRAO_HORAS.items():
        valores = list(RegraSLA.objects.filter(prioridade=p).values_list("horas_uteis", flat=True))
        out[p] = max(set(valores), key=valores.count) if valores else padrao
    return out


def simular(horas: dict) -> dict:
    """'Com estas regras, 31 dos 34 chamados abertos estariam no prazo (91%)'."""
    agora = timezone.now()
    feriados = feriados_do_sistema(agora.year)
    abertos = Chamado.objects.filter(status__in=STATUS_ABERTOS).only("criado_em", "prioridade")
    total = no_prazo = 0
    for c in abertos:
        total += 1
        h = int(horas.get(c.prioridade, 0))
        if h > 0 and somar_horas_uteis(c.criado_em, h, feriados) >= agora:
            no_prazo += 1
    return {"total": total, "no_prazo": no_prazo, "percentual": round(100 * no_prazo / total) if total else 100}


@login_required
def config(request):
    _exige_modulo(request, "config", "E")
    horas = _horas_por_prioridade()
    matriz = {(p.papel, p.modulo): p.nivel for p in PermissaoModulo.objects.all()}
    ctx = {
        "sla": [(p, Chamado.Prioridade(p).label, EXEMPLOS[p], horas[p]) for p in SLA_PADRAO_HORAS],
        "simulacao": simular(horas),
        "papeis": PAPEIS_MATRIZ, "modulos": [(m, ROTULOS_MODULO[m]) for m in papeis.MODULOS],
        "matriz": {f"{p}:{m}": matriz.get((p, m), "-") for p in PAPEIS_MATRIZ for m in papeis.MODULOS},
        "tipos": TipoTrabalho.objects.all(), "motivos": MotivoRetrabalho.objects.all(),
        "categorias": Categoria.objects.all(), "setores": Setor.objects.filter(ativo=True).prefetch_related("centros_custo"),
    }
    return render(request, "web/config/tela.html", ctx)


@login_required
def simular_sla(request):
    _exige_modulo(request, "config", "E")
    horas = {p: int(request.GET.get(p) or 0) for p in SLA_PADRAO_HORAS}
    return JsonResponse(simular(horas))


@login_required
@require_POST
def salvar_sla(request):
    """Aplica as horas por prioridade a todas as categorias (uma regra por categoria × prioridade)."""
    _exige_modulo(request, "config", "E")
    antes = _horas_por_prioridade()
    for cat in Categoria.objects.all():
        for p in SLA_PADRAO_HORAS:
            h = int(request.POST.get(p) or antes[p])
            RegraSLA.objects.update_or_create(categoria=cat, prioridade=p, defaults={"horas_uteis": h})
    depois = _horas_por_prioridade()
    registrar(usuario=request.user, acao="sla.alterar_global", objeto=request.user, antes=antes, depois=depois)
    r = HttpResponse(status=204)
    r["HX-Refresh"] = "true"
    return r


@login_required
@require_POST
def alternar_permissao(request):
    """Célula clicável: ver → editar → sem acesso → ver…"""
    _exige_modulo(request, "config", "E")
    papel, modulo = request.POST.get("papel"), request.POST.get("modulo")
    if papel not in PAPEIS_MATRIZ or modulo not in papeis.MODULOS:
        return HttpResponse(status=400)
    perm, _ = PermissaoModulo.objects.get_or_create(papel=papel, modulo=modulo, defaults={"nivel": "-"})
    proximo = {"V": "E", "E": "-", "-": "V"}[perm.nivel]
    registrar(usuario=request.user, acao="permissao.alterar", objeto=perm, antes={"nivel": perm.nivel}, depois={"nivel": proximo})
    perm.nivel = proximo
    perm.save(update_fields=["nivel"])
    invalidar_matriz()
    return render(request, "web/config/_celula.html", {"papel": papel, "modulo": modulo, "nivel": proximo})


@login_required
@require_POST
def alternar_flag(request, modelo, pk, campo):
    """Cadastros simples: tipos (exige_causa/contabiliza), categorias (exige_documentacao)."""
    _exige_modulo(request, "config", "E")
    modelos = {"tipo": (TipoTrabalho, {"exige_causa", "contabiliza_capacidade"}), "categoria": (Categoria, {"exige_documentacao"})}
    if modelo not in modelos or campo not in modelos[modelo][1]:
        return HttpResponse(status=400)
    obj = modelos[modelo][0].objects.get(pk=pk)
    antes = getattr(obj, campo)
    setattr(obj, campo, not antes)
    obj.save(update_fields=[campo])
    registrar(usuario=request.user, acao=f"{modelo}.{campo}", objeto=obj, antes={campo: antes}, depois={campo: not antes})
    r = HttpResponse(status=204)
    r["HX-Refresh"] = "true"
    return r


@login_required
@require_POST
def novo_cadastro(request, modelo):
    _exige_modulo(request, "config", "E")
    nome = request.POST.get("nome", "").strip()
    if not nome:
        return HttpResponse(status=400)
    if modelo == "motivo":
        MotivoRetrabalho.objects.get_or_create(nome=nome)
    elif modelo == "tipo":
        from django.utils.text import slugify

        TipoTrabalho.objects.get_or_create(slug=slugify(nome), defaults={"nome": nome, "ordem": TipoTrabalho.objects.count()})
    elif modelo == "categoria":
        from django.utils.text import slugify

        Categoria.objects.get_or_create(slug=slugify(nome), defaults={"nome": nome})
    elif modelo == "centro_custo":
        setor = Setor.objects.get(pk=request.POST.get("setor"))
        CentroCusto.objects.get_or_create(codigo=request.POST.get("codigo", "").strip(), defaults={"descricao": nome, "setor": setor})
    else:
        return HttpResponse(status=400)
    r = HttpResponse(status=204)
    r["HX-Refresh"] = "true"
    return r


@login_required
def historico_mudancas(request):
    """Tela transversal: quem mudou o quê. Gerentes, Compras e Admin."""
    from core.permissions import papeis_de

    if not papeis_de(request.user) & {papeis.GERENTE_TI, papeis.ADMINISTRADOR, papeis.GERENTE_SETOR, papeis.COMPRAS}:
        from django.http import Http404

        raise Http404
    qs = Auditoria.objects.select_related("usuario")
    p = request.GET
    if objeto := p.get("objeto"):
        tipo, _, oid = objeto.partition(":")
        qs = qs.filter(objeto_tipo=tipo)
        if oid:
            qs = qs.filter(objeto_id=oid)
    if p.get("usuario"):
        qs = qs.filter(usuario_id=p["usuario"])
    if p.get("acao"):
        qs = qs.filter(acao__startswith=p["acao"])
    from django.core.paginator import Paginator

    from core.models import User

    pagina = Paginator(qs, 100).get_page(p.get("pagina"))
    ctx = {"pagina": pagina, "usuarios": User.objects.filter(is_active=True).order_by("first_name"),
           "tipos": Auditoria.objects.values_list("objeto_tipo", flat=True).distinct().order_by("objeto_tipo"), "filtros": p}  # fmt: skip
    return render(request, "web/config/historico.html", ctx)
