"""Projetos de TI: kanban de 8 fases + histórico, marcos e alocação."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Sum

from core.auditoria import registrar

from .exceptions import AlocacaoExcedida, EncerramentoSemData, FaseInvalida, ProjetoEncerrado
from .models import FASES_HISTORICO, FASES_KANBAN, Alocacao, Marco, Projeto

F = Projeto.Fase
ENCERRAMENTO_EXIGE_DOC = {F.IMPLANTACAO, F.CONCLUIDO}


def fases_permitidas(de: str) -> set[str]:
    """Kanban: avança uma, volta quantas quiser; cancelar de qualquer aberta; concluir só de implantação."""
    if de in FASES_HISTORICO:
        return set()
    i = FASES_KANBAN.index(de)
    permitidas = set(FASES_KANBAN[: i + 2])  # todas as anteriores + a próxima
    permitidas.discard(de)
    permitidas.add(F.CANCELADO)
    if de == F.IMPLANTACAO:
        permitidas.add(F.CONCLUIDO)
    return permitidas


@transaction.atomic
def criar_projeto(*, usuario, **dados) -> Projeto:
    p = Projeto.objects.create(criado_por=usuario, **dados)
    registrar(usuario=usuario, acao="projeto.criar", objeto=p, antes=None, depois={"fase": p.fase})
    return p


@transaction.atomic
def editar_projeto(*, projeto: Projeto, usuario, **campos) -> Projeto:
    p = Projeto.objects.select_for_update().get(pk=projeto.pk)
    if p.fase in FASES_HISTORICO:
        raise ProjetoEncerrado()
    antes = {k: _s(getattr(p, k)) for k in campos}
    for k, v in campos.items():
        setattr(p, k, v)
    p.save(update_fields=[*campos, "atualizado_em"])
    registrar(usuario=usuario, acao="projeto.editar", objeto=p, antes=antes, depois={k: _s(v) for k, v in campos.items()})
    return p


@transaction.atomic
def mover_fase(*, projeto: Projeto, para: str, usuario, encerrado_em=None, situacao_final: str = "") -> Projeto:
    p = Projeto.objects.select_for_update().get(pk=projeto.pk)
    de = p.fase
    if para not in fases_permitidas(de):
        raise FaseInvalida(de, para)
    if para in FASES_HISTORICO:
        if not encerrado_em or not situacao_final.strip():
            raise EncerramentoSemData()
        p.encerrado_em = encerrado_em
        p.situacao_final = situacao_final.strip()
    if para == F.IMPLANTACAO:
        _avisar_documentacao(p)
    p.fase = para
    p.save(update_fields=["fase", "encerrado_em", "situacao_final", "atualizado_em"])
    registrar(usuario=usuario, acao="projeto.mover_fase", objeto=p, antes={"fase": de},
              depois={"fase": para, "encerrado_em": _s(p.encerrado_em)})  # fmt: skip
    return p


def _avisar_documentacao(p: Projeto) -> None:
    """Regra do modal: 'projetos com mudança de regra exigem documentação antes da implantação'.
    Nesta fase é aviso (fica no histórico de auditoria); o bloqueio duro é decisão de produto."""
    from documentacao.models import Documento

    if not Documento.objects.filter(projeto=p, secao="regra", versao_atual__publicada_em__isnull=False).exists():
        registrar(usuario=None, acao="projeto.aviso_documentacao", objeto=p, antes=None,
                  depois={"mensagem": "Implantação sem seção 'Regra de negócio' publicada"})  # fmt: skip


@transaction.atomic
def adicionar_marco(*, projeto: Projeto, usuario, nome: str, previsto) -> Marco:
    if projeto.fase in FASES_HISTORICO:
        raise ProjetoEncerrado()
    m = Marco.objects.create(projeto=projeto, nome=nome, previsto=previsto)
    registrar(usuario=usuario, acao="projeto.marco", objeto=projeto, antes=None, depois={"marco": nome, "previsto": _s(previsto)})
    return m


@transaction.atomic
def concluir_marco(*, marco: Marco, usuario, concluido_em) -> Marco:
    marco.concluido_em = concluido_em
    marco.save(update_fields=["concluido_em"])
    registrar(usuario=usuario, acao="projeto.marco_concluido", objeto=marco.projeto, antes=None,
              depois={"marco": marco.nome, "concluido_em": _s(concluido_em)})  # fmt: skip
    return marco


LIMITE_ALOCACAO = 100


@transaction.atomic
def alocar(*, projeto: Projeto, usuario_alocado, percentual: int, usuario) -> Alocacao:
    """Soma das alocações de uma pessoa em projetos abertos não passa de 100%."""
    if projeto.fase in FASES_HISTORICO:
        raise ProjetoEncerrado()
    outras = (
        Alocacao.objects.filter(usuario=usuario_alocado, projeto__fase__in=FASES_KANBAN)
        .exclude(projeto=projeto)
        .aggregate(t=Sum("percentual"))["t"] or 0
    )
    if outras + percentual > LIMITE_ALOCACAO:
        raise AlocacaoExcedida(usuario_alocado, outras + percentual)
    aloc, _ = Alocacao.objects.update_or_create(
        projeto=projeto, usuario=usuario_alocado, defaults={"percentual": percentual}
    )
    registrar(usuario=usuario, acao="projeto.alocar", objeto=projeto, antes=None,
              depois={"usuario": usuario_alocado.pk, "percentual": percentual})  # fmt: skip
    return aloc


def _s(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v.pk if hasattr(v, "pk") else v
