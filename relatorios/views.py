"""Relatórios. Todos aceitam `?formato=json|csv|xlsx|pdf` (ver `export.responder`)."""

from datetime import date


from django.utils.dateparse import parse_date
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from almoxarifado import selectors as almox
from apontamentos import selectors
from core import papeis
from core.models import Auditoria, Setor
from core.permissions import papeis_de, ve_todos_setores

from . import selectors as rel
from .export import responder


def _periodo(request) -> tuple[date | None, date | None]:
    return parse_date(request.query_params.get("de") or ""), parse_date(request.query_params.get("ate") or "")


def _setor(request):
    """Setor efetivo: quem vê todos escolhe (`?setor=`), os demais ficam presos ao próprio."""
    user = request.user
    if ve_todos_setores(user):
        sid = request.query_params.get("setor")
        return Setor.objects.filter(pk=sid).first() if sid else None
    return user.setor


def _escopo(request):
    """Mesmo escopo dos apontamentos: Colaborador só o seu; Resp/Gerente o setor; TI+ o que pedir."""
    user = request.user
    de, ate = _periodo(request)
    if ve_todos_setores(user):
        return selectors.validos(de, ate, setor=_setor(request))
    if papeis_de(user) & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}:
        return selectors.validos(de, ate, setor=user.setor)
    return selectors.validos(de, ate, usuario=user)


class RelatorioHorasView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _escopo(request)
        if tipo := request.query_params.get("tipo"):
            qs = qs.filter(tipo__slug=tipo)
        por_tipo = selectors.horas_por_tipo(qs)
        por_pessoa = selectors.horas_por_pessoa(qs)
        dados = {"por_tipo": por_tipo, "por_pessoa": por_pessoa, "por_chamado": selectors.horas_por_chamado(qs),
                 "total_min": sum(l["minutos"] for l in por_tipo)}  # fmt: skip
        return responder(request, dados_json=dados, nome="horas",
                         colunas=["nome", "sobrenome", "setor", "minutos", "retrabalho_min"], linhas=por_pessoa)  # fmt: skip


class RelatorioRetrabalhoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _escopo(request)
        por_motivo = selectors.retrabalho_por_motivo(qs)
        dados = {**selectors.percentual_retrabalho(qs), "por_motivo": por_motivo,
                 "por_origem": selectors.retrabalho_por_origem(qs)}  # fmt: skip
        return responder(request, dados_json=dados, nome="retrabalho",
                         colunas=["motivo", "minutos", "apontamentos"], linhas=por_motivo)  # fmt: skip


class RelatorioConsumoView(APIView):
    """Consumo de almoxarifado. `?sem_os=true` = consumo geral (desperdício, regra §8)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from almoxarifado.serializers import MovimentoSerializer

        de, ate = _periodo(request)
        sem_os = request.query_params.get("sem_os")
        sem_os = None if sem_os is None else sem_os in ("true", "1")
        qs = almox.consumo(de, ate, setor=_setor(request), sem_os=sem_os)
        movimentos = MovimentoSerializer(qs.order_by("-criado_em"), many=True).data
        linhas = [{"quando": m["criado_em"], "item": m["item"]["codigo"], "descricao": m["item"]["descricao"],
                   "setor": m["setor"]["sigla"], "quantidade": m["quantidade"], "centro_custo": m["centro_custo"],
                   "os_ref": m["os_ref"], "consumo_geral": m["consumo_geral"], "usuario": m["usuario"]["nome"]}
                  for m in movimentos]  # fmt: skip
        dados = {"por_setor": almox.consumo_por_setor(qs), "movimentos": movimentos[:500]}
        return responder(request, dados_json=dados, nome="consumo", linhas=linhas,
                         colunas=["quando", "item", "descricao", "setor", "quantidade", "centro_custo", "os_ref", "consumo_geral", "usuario"])  # fmt: skip


class RelatorioSLAView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        de, ate = _periodo(request)
        dados = rel.sla(de, ate, setor=_setor(request))
        return responder(request, dados_json=dados, nome="sla",
                         colunas=["categoria", "total", "cumpridos", "percentual"], linhas=dados["por_categoria"])  # fmt: skip


class RelatorioAuditoriaView(APIView):
    """Histórico de mudanças. `?objeto=chamados.chamado:42` ou `?tipo=&acao=&usuario=`."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        meus = papeis_de(request.user)
        if not meus & {papeis.GERENTE_TI, papeis.ADMINISTRADOR, papeis.GERENTE_SETOR, papeis.COMPRAS}:
            return Response({"erro": "sem_permissao"}, status=403)
        qs = Auditoria.objects.select_related("usuario")
        p = request.query_params
        if objeto := p.get("objeto"):
            tipo, _, oid = objeto.partition(":")
            qs = qs.filter(objeto_tipo=tipo)
            if oid:
                qs = qs.filter(objeto_id=oid)
        if tipo := p.get("tipo"):
            qs = qs.filter(objeto_tipo=tipo)
        if acao := p.get("acao"):
            qs = qs.filter(acao__startswith=acao)
        if uid := p.get("usuario"):
            qs = qs.filter(usuario_id=uid)
        de, ate = _periodo(request)
        if de:
            qs = qs.filter(quando__date__gte=de)
        if ate:
            qs = qs.filter(quando__date__lte=ate)
        linhas = [{"quando": a.quando, "usuario": a.usuario.nome if a.usuario else "sistema", "acao": a.acao,
                   "objeto": f"{a.objeto_tipo}:{a.objeto_id}", "antes": a.antes, "depois": a.depois}
                  for a in qs[:2000]]  # fmt: skip
        return responder(request, dados_json={"registros": linhas, "total": qs.count()}, nome="auditoria",
                         colunas=["quando", "usuario", "acao", "objeto", "antes", "depois"], linhas=linhas)  # fmt: skip


class PainelView(APIView):
    """Todos os KPIs da tela de indicadores em uma chamada. Período padrão: mês corrente."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.permissions import nivel_no_modulo

        if nivel_no_modulo(request.user, "painel") == "-":
            return Response({"erro": "sem_permissao"}, status=403)
        de, ate = _periodo(request)
        dados = rel.painel(user=request.user, de=de, ate=ate, setor=_setor(request))
        dados.pop("risco_sla_objetos", None)
        return Response(dados)
