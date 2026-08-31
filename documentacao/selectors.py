"""Leitura: seções faltantes, status por seção, cobertura e pendências para o painel."""

from __future__ import annotations

from django.db.models import Count, Q

from chamados.models import Chamado

from .models import SECOES_OBRIGATORIAS, Documento


def base_listagem():
    return Documento.objects.select_related(
        "chamado", "chamado__setor_origem", "chamado__categoria", "projeto",
        "versao_atual", "versao_atual__autor",
    ).prefetch_related("versoes")  # fmt: skip


def secoes_publicadas(chamado) -> set[str]:
    return set(
        Documento.objects.filter(chamado=chamado, versao_atual__publicada_em__isnull=False)
        .values_list("secao", flat=True)
    )


def secoes_faltantes(chamado) -> list[str]:
    """Rótulos das seções obrigatórias sem versão publicada, na ordem canônica (regra §5)."""
    publicadas = secoes_publicadas(chamado)
    return [Documento.Secao(s).label for s in SECOES_OBRIGATORIAS if s not in publicadas]


def status_documento(doc: Documento) -> str:
    """'publicado' | 'rascunho' | 'falta' — o chip do card."""
    atual = doc.versao_atual
    if atual is not None and atual.publicada_em:
        return "publicado"
    if any(v.publicada_em is None for v in doc.versoes.all()):
        return "rascunho"
    return "falta"


def cobertura(*, setor=None, de=None, ate=None) -> dict:
    """Percentual do painel: seções obrigatórias publicadas / (4 × chamados entregues no período).

    Conta as 4 seções de SECOES_OBRIGATORIAS para toda categoria — nas que não exigem
    documentação a ausência não bloqueia a entrega, só derruba este número (regra §5).
    """
    entregues = Chamado.objects.filter(status=Chamado.Status.ENTREGUE)
    if setor:
        entregues = entregues.filter(setor_origem=setor)
    if de:
        entregues = entregues.filter(entregue_em__date__gte=de)
    if ate:
        entregues = entregues.filter(entregue_em__date__lte=ate)
    total_chamados = entregues.count()
    aplicaveis = total_chamados * len(SECOES_OBRIGATORIAS)
    publicadas = Documento.objects.filter(
        chamado__in=entregues, secao__in=SECOES_OBRIGATORIAS, versao_atual__publicada_em__isnull=False
    ).count()
    return {
        "chamados_entregues": total_chamados,
        "secoes_aplicaveis": aplicaveis,
        "secoes_publicadas": publicadas,
        "percentual": round(100 * publicadas / aplicaveis, 1) if aplicaveis else 0.0,
    }


def documentacao_pendente(qs=None):
    """Card 'Documentação pendente': chamados entregáveis (em testes) travados por documentação."""
    qs = qs if qs is not None else Chamado.objects.all()
    candidatos = (
        qs.filter(status=Chamado.Status.TESTES, categoria__exige_documentacao=True)
        .annotate(
            publicadas=Count(
                "documentos",
                filter=Q(documentos__secao__in=SECOES_OBRIGATORIAS,
                         documentos__versao_atual__publicada_em__isnull=False),
            )
        )  # fmt: skip
        .filter(publicadas__lt=len(SECOES_OBRIGATORIAS))
        .select_related("setor_origem", "responsavel", "categoria")
        .order_by("sla_previsto")
    )
    return [(c, secoes_faltantes(c)) for c in candidatos]
