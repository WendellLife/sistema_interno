"""Toda a regra de negócio de chamados. Views e tasks apenas chamam estas funções."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core import papeis
from core.auditoria import registrar
from core.calendario import feriados_do_sistema, somar_horas_uteis
from core.numeracao import proximo_numero
from core.permissions import papeis_de

from .exceptions import (
    DocumentacaoIncompleta,
    JustificativaObrigatoria,
    SemPermissaoParaAcao,
    TransicaoInvalida,
)
from .models import SLA_PADRAO_HORAS, Anexo, Chamado, Comentario, HistoricoChamado, RegraSLA

S = Chamado.Status

# Máquina de estados (04-API-E-PERMISSOES.md §2). `cancelado` é tratado à parte.
TRANSICOES: dict[str, set[str]] = {
    S.NOVO: {S.TRIAGEM},
    S.TRIAGEM: {S.FILA},
    S.FILA: {S.EXECUCAO},
    S.EXECUCAO: {S.TESTES, S.AGUARDA_SOLICITANTE},
    S.TESTES: {S.ENTREGUE, S.AGUARDA_SOLICITANTE},
    S.AGUARDA_SOLICITANTE: {S.EXECUCAO, S.TESTES},
    S.ENTREGUE: set(),
    S.CANCELADO: set(),
}

PAPEIS_PODEM_CANCELAR = {
    papeis.RESPONSAVEL, papeis.GERENTE_SETOR, papeis.GERENTE_TI, papeis.ADMINISTRADOR,
}  # fmt: skip


# ---------------------------------------------------------------- SLA


def horas_uteis_sla(categoria, prioridade: str) -> int:
    regra = RegraSLA.objects.filter(categoria=categoria, prioridade=prioridade).first()
    return regra.horas_uteis if regra else SLA_PADRAO_HORAS[prioridade]


def calcular_sla(chamado: Chamado):
    """SLA sempre a partir da abertura original — mudança de prioridade recalcula daqui."""
    base = chamado.criado_em or timezone.now()
    horas = horas_uteis_sla(chamado.categoria, chamado.prioridade)
    feriados = feriados_do_sistema(base.year) | feriados_do_sistema(base.year + 1)
    return somar_horas_uteis(base, horas, feriados)


# ---------------------------------------------------------------- histórico


def _historico(chamado: Chamado, usuario, texto: str) -> None:
    HistoricoChamado.objects.create(chamado=chamado, usuario=usuario, texto=texto[:240])


# ---------------------------------------------------------------- abertura


@transaction.atomic
def abrir_chamado(
    *,
    solicitante,
    titulo: str,
    descricao: str,
    categoria,
    prioridade: str,
    setor_origem=None,
    projeto=None,
    horas_previstas_min: int = 0,
) -> Chamado:
    setor_origem = setor_origem or solicitante.setor
    chamado = Chamado.objects.create(
        numero=proximo_numero("TI"),
        titulo=titulo,
        descricao=descricao,
        setor_origem=setor_origem,
        solicitante=solicitante,
        categoria=categoria,
        prioridade=prioridade,
        projeto=projeto,
        horas_previstas_min=horas_previstas_min,
        criado_por=solicitante,
    )
    chamado.sla_previsto = calcular_sla(chamado)
    chamado.save(update_fields=["sla_previsto"])
    from documentacao.services import criar_secoes

    criar_secoes(chamado=chamado, criado_por=solicitante)
    _historico(chamado, solicitante, f"Chamado aberto por {solicitante.nome} ({setor_origem.sigla})")
    registrar(
        usuario=solicitante,
        acao="chamado.abrir",
        objeto=chamado,
        antes=None,
        depois={"status": chamado.status, "prioridade": prioridade, "numero": chamado.numero},
    )
    return chamado


# ---------------------------------------------------------------- entrega


def pode_entregar(chamado: Chamado) -> tuple[bool, list[str]]:
    """Regra §5: categorias com exige_documentacao só entregam com as 4 seções publicadas."""
    if not chamado.categoria.exige_documentacao:
        return True, []
    from documentacao.selectors import secoes_faltantes

    faltando = secoes_faltantes(chamado)
    return not faltando, faltando


# ---------------------------------------------------------------- transições


@transaction.atomic
def transicionar(*, chamado: Chamado, para: str, usuario, comentario: str = "") -> Chamado:
    """Aplica uma transição da máquina de estados. Para `cancelado`, use `cancelar()`."""
    chamado = Chamado.objects.select_for_update().select_related("categoria").get(pk=chamado.pk)
    de = chamado.status
    if para == S.CANCELADO:
        return cancelar(chamado=chamado, usuario=usuario, justificativa=comentario)
    if para not in TRANSICOES.get(de, set()):
        raise TransicaoInvalida(de, para)

    if para == S.ENTREGUE:
        ok, faltando = pode_entregar(chamado)
        if not ok:
            raise DocumentacaoIncompleta(faltando)
        agora = timezone.now()
        chamado.entregue_em = agora
        chamado.sla_cumprido = bool(chamado.sla_previsto and agora <= chamado.sla_previsto)

    chamado.status = para
    chamado.save(update_fields=["status", "entregue_em", "sla_cumprido", "atualizado_em"])

    texto = f"{S(de).label} → {S(para).label}"
    if comentario:
        texto += f": {comentario}"
    _historico(chamado, usuario, texto)
    if comentario:
        Comentario.objects.create(chamado=chamado, autor=usuario, texto=comentario, criado_por=usuario)
    registrar(
        usuario=usuario,
        acao=f"chamado.{para}" if para == S.ENTREGUE else "chamado.transicionar",
        objeto=chamado,
        antes={"status": de},
        depois={"status": para, "sla_cumprido": chamado.sla_cumprido},
    )
    return chamado


def entregar_chamado(*, chamado: Chamado, usuario, comentario: str = "") -> Chamado:
    return transicionar(chamado=chamado, para=S.ENTREGUE, usuario=usuario, comentario=comentario)


@transaction.atomic
def cancelar(*, chamado: Chamado, usuario, justificativa: str) -> Chamado:
    if not (papeis_de(usuario) & PAPEIS_PODEM_CANCELAR):
        raise SemPermissaoParaAcao("Apenas Responsável do setor ou acima pode cancelar.")
    if not justificativa or len(justificativa.strip()) < 5:
        raise JustificativaObrigatoria()
    chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
    de = chamado.status
    if de in (S.ENTREGUE, S.CANCELADO):
        raise TransicaoInvalida(de, S.CANCELADO)
    chamado.status = S.CANCELADO
    chamado.save(update_fields=["status", "atualizado_em"])
    _historico(chamado, usuario, f"Cancelado: {justificativa}")
    Comentario.objects.create(chamado=chamado, autor=usuario, texto=justificativa, criado_por=usuario)
    registrar(
        usuario=usuario,
        acao="chamado.cancelar",
        objeto=chamado,
        antes={"status": de},
        depois={"status": S.CANCELADO, "justificativa": justificativa},
    )
    return chamado


# ---------------------------------------------------------------- edição


@transaction.atomic
def alterar_prioridade(*, chamado: Chamado, prioridade: str, usuario) -> Chamado:
    chamado = Chamado.objects.select_for_update().select_related("categoria").get(pk=chamado.pk)
    antes = {"prioridade": chamado.prioridade, "sla_previsto": _iso(chamado.sla_previsto)}
    if chamado.prioridade == prioridade:
        return chamado
    chamado.prioridade = prioridade
    chamado.sla_previsto = calcular_sla(chamado)
    chamado.save(update_fields=["prioridade", "sla_previsto", "atualizado_em"])
    _historico(
        chamado,
        usuario,
        f"Prioridade {Chamado.Prioridade(antes['prioridade']).label} → "
        f"{Chamado.Prioridade(prioridade).label}; SLA recalculado para "
        f"{timezone.localtime(chamado.sla_previsto):%d/%m %H:%M}",
    )
    registrar(
        usuario=usuario,
        acao="chamado.alterar_prioridade",
        objeto=chamado,
        antes=antes,
        depois={"prioridade": prioridade, "sla_previsto": _iso(chamado.sla_previsto)},
    )
    return chamado


@transaction.atomic
def atribuir(*, chamado: Chamado, responsavel, usuario) -> Chamado:
    chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
    antes = chamado.responsavel_id
    chamado.responsavel = responsavel
    chamado.save(update_fields=["responsavel", "atualizado_em"])
    _historico(
        chamado, usuario, f"Atribuído a {responsavel.nome}" if responsavel else "Responsável removido"
    )
    registrar(
        usuario=usuario,
        acao="chamado.atribuir",
        objeto=chamado,
        antes={"responsavel": antes},
        depois={"responsavel": responsavel.pk if responsavel else None},
    )
    return chamado


@transaction.atomic
def editar(*, chamado: Chamado, usuario, **campos) -> Chamado:
    """Edição de campos simples (título, descrição, horas previstas, projeto) com auditoria."""
    chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
    antes = {k: _serializavel(getattr(chamado, k)) for k in campos}
    for campo, valor in campos.items():
        setattr(chamado, campo, valor)
    chamado.save(update_fields=[*campos.keys(), "atualizado_em"])
    registrar(
        usuario=usuario,
        acao="chamado.editar",
        objeto=chamado,
        antes=antes,
        depois={k: _serializavel(v) for k, v in campos.items()},
    )
    return chamado


def comentar(*, chamado: Chamado, autor, texto: str, interno: bool = False) -> Comentario:
    return Comentario.objects.create(
        chamado=chamado, autor=autor, texto=texto, interno=interno, criado_por=autor
    )


def anexar(*, chamado: Chamado, usuario, arquivo) -> Anexo:
    anexo = Anexo.objects.create(
        chamado=chamado,
        arquivo=arquivo,
        nome_original=arquivo.name[:180],
        tamanho_bytes=arquivo.size,
        criado_por=usuario,
    )
    _historico(chamado, usuario, f"Anexo adicionado: {anexo.nome_original}")
    return anexo


# ---------------------------------------------------------------- SLA vencido (task)


def marcar_slas_vencidos() -> int:
    """Marca `sla_cumprido=False` nos abertos com SLA vencido, sem fechar o chamado."""
    from .models import STATUS_ABERTOS

    return Chamado.objects.filter(
        status__in=STATUS_ABERTOS, sla_previsto__lt=timezone.now(), sla_cumprido__isnull=True
    ).update(sla_cumprido=False)


def _serializavel(v):
    return v.pk if hasattr(v, "pk") else v


def _iso(dt):
    return dt.isoformat() if dt else None
