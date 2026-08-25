"""Busca global: full-text português + trigram, escopada pelo papel. Máx. 5 por tipo."""

from __future__ import annotations

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramSimilarity
from django.db.models import F, Q, Value
from django.db.models.functions import Greatest

from almoxarifado.models import Item, Solicitacao
from almoxarifado.permissions import COMPRAS_OU_ADMIN, tem_papel
from almoxarifado.models import Item, Solicitacao
from chamados.models import Chamado
from core import papeis
from core.permissions import papeis_de, ve_todos_setores
from projetos.models import Projeto

LIMITE_POR_TIPO = 5
SIMILARIDADE_MIN = 0.15


def _escopo_chamados(user):
    qs = Chamado.objects.select_related("setor_origem")
    if ve_todos_setores(user):
        return qs
    if papeis_de(user) & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}:
        return qs.filter(setor_origem=user.setor)
    return qs.filter(Q(solicitante=user) | Q(responsavel=user))


def _escopo_projetos(user):
    qs = Projeto.objects.select_related("setor_solicitante")
    if ve_todos_setores(user):
        return qs
    if papeis_de(user) & {papeis.RESPONSAVEL, papeis.GERENTE_SETOR}:
        return qs.filter(setor_solicitante=user.setor)
    return qs.none()


def _rankear(qs, q: str, campo_titulo: str, campo_texto: str, campo_codigo: str | None = None):
    vetor = SearchVector(campo_titulo, weight="A", config="portuguese") + SearchVector(
        campo_texto, weight="B", config="portuguese"
    )
    consulta = SearchQuery(q, config="portuguese", search_type="websearch")
    similaridade = TrigramSimilarity(campo_titulo, q)
    if campo_codigo:
        similaridade = Greatest(similaridade, TrigramSimilarity(campo_codigo, q))
    return (
        qs.annotate(rank=SearchRank(vetor, consulta), sim=similaridade)
        .annotate(pontos=Greatest(F("rank"), F("sim"), Value(0.0)))
        .filter(Q(rank__gt=0) | Q(sim__gte=SIMILARIDADE_MIN))
        .order_by("-pontos")[:LIMITE_POR_TIPO]
    )


def buscar(*, user, q: str) -> list[dict]:
    q = (q or "").strip()
    if len(q) < 2:
        return []
    resultados: list[dict] = []
    for c in _rankear(_escopo_chamados(user), q, "titulo", "descricao", "numero"):
        resultados.append({
            "tipo": "chamado", "id": c.id, "titulo": f"{c.numero} — {c.titulo}",
            "subtitulo": f"{c.setor_origem.sigla} · {c.get_status_display()}",
            "url": f"/tarefas/{c.id}",
        })  # fmt: skip
    for p in _rankear(_escopo_projetos(user), q, "nome", "situacao_final"):
        resultados.append({
            "tipo": "projeto", "id": p.id, "titulo": p.nome,
            "subtitulo": f"{p.setor_solicitante.sigla} · {p.get_fase_display()}",
            "url": f"/projetos/{p.id}",
        })  # fmt: skip
    for i in _rankear(Item.objects.filter(ativo=True).select_related("setor_dono"), q, "descricao", "codigo_sankhya", "codigo"):
        resultados.append({
            "tipo": "item", "id": i.id, "titulo": f"{i.codigo} — {i.descricao}",
            "subtitulo": f"{i.unidade} · {i.setor_dono.sigla}", "url": f"/almoxarifado/itens/{i.id}",
        })  # fmt: skip
    sols = Solicitacao.objects.select_related("setor")
    if not tem_papel(user, COMPRAS_OU_ADMIN):
        sols = sols.filter(setor=user.setor)
    for s in _rankear(sols, q, "numero", "observacao", "os_ref"):
        resultados.append({
            "tipo": "solicitacao", "id": s.id, "titulo": s.numero,
            "subtitulo": f"{s.setor.sigla} · {s.get_status_display()}", "url": f"/almoxarifado/solicitacoes/{s.id}",
        })  # fmt: skip
    return resultados
