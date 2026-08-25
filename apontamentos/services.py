"""Regras de apontamento: causa em retrabalho, cronômetro único, não sobreposição, aprovação."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from core import papeis
from core.auditoria import registrar
from core.permissions import papeis_de

from .exceptions import (
    ApontamentoNaoPendente,
    CausaObrigatoria,
    ConflitoDeHoras,
    ForaDoEscopoDeAprovacao,
    SemCronometroAberto,
)
from .models import Apontamento, TipoTrabalho

DIAS_RETROATIVO_EXIGE_APROVACAO = 7
DETALHE_RETRABALHO_MIN = 15


# ---------------------------------------------------------------- validações


def _validar_causa(tipo: TipoTrabalho, motivo_retrabalho, detalhe_retrabalho: str) -> None:
    if not tipo.exige_causa:
        return
    if motivo_retrabalho is None:
        raise CausaObrigatoria()
    if len((detalhe_retrabalho or "").strip()) < DETALHE_RETRABALHO_MIN:
        raise CausaObrigatoria(
            "detalhe_retrabalho", f"Descreva o retrabalho com pelo menos {DETALHE_RETRABALHO_MIN} caracteres."
        )


def _validar_destino(chamado, projeto) -> None:
    if chamado is None and projeto is None:
        raise CausaObrigatoria("chamado", "Informe um chamado ou um projeto.")


def _conflitante(usuario, inicio: datetime, fim: datetime | None, excluir_id=None):
    """Primeiro apontamento do usuário que se sobrepõe a [inicio, fim). fim=None = aberto."""
    qs = Apontamento.objects.filter(usuario=usuario).select_related("tipo")
    if excluir_id:
        qs = qs.exclude(pk=excluir_id)
    qs = qs.filter(fim__gt=inicio) | qs.filter(fim__isnull=True)
    if fim is not None:
        qs = qs.filter(inicio__lt=fim)
    return qs.order_by("inicio").first()


def _minutos(inicio: datetime, fim: datetime) -> int:
    return max(1, int((fim - inicio).total_seconds() // 60))


# ---------------------------------------------------------------- cronômetro


def cronometro_aberto(usuario) -> Apontamento | None:
    return (
        Apontamento.objects.filter(usuario=usuario, fim__isnull=True)
        .select_related("tipo", "chamado", "projeto")
        .first()
    )


@transaction.atomic
def fechar_apontamento(apontamento: Apontamento, *, fim: datetime, usuario=None) -> Apontamento:
    apontamento.fim = fim
    apontamento.minutos = _minutos(apontamento.inicio, fim)
    apontamento.save(update_fields=["fim", "minutos", "atualizado_em"])
    registrar(
        usuario=usuario or apontamento.usuario,
        acao="apontamento.fechar",
        objeto=apontamento,
        antes={"fim": None},
        depois={"fim": fim.isoformat(), "minutos": apontamento.minutos},
    )
    return apontamento


@transaction.atomic
def iniciar_cronometro(
    *, usuario, tipo, chamado=None, projeto=None, motivo_retrabalho=None,
    detalhe_retrabalho: str = "", observacao: str = "",
) -> tuple[Apontamento, Apontamento | None]:  # fmt: skip
    """Abre um cronômetro; o anterior do mesmo usuário é fechado na mesma transação.
    Retorna (novo, pausado_ou_None)."""
    _validar_destino(chamado, projeto)
    _validar_causa(tipo, motivo_retrabalho, detalhe_retrabalho)
    agora = timezone.now()
    anterior = (
        Apontamento.objects.select_for_update()
        .select_related("tipo")
        .filter(usuario=usuario, fim__isnull=True)
        .first()
    )
    if anterior:
        fechar_apontamento(anterior, fim=agora, usuario=usuario)
    if conflito := _conflitante(usuario, agora, None):
        raise ConflitoDeHoras(conflito)
    novo = Apontamento.objects.create(
        usuario=usuario, tipo=tipo, chamado=chamado, projeto=projeto, inicio=agora,
        motivo_retrabalho=motivo_retrabalho, detalhe_retrabalho=detalhe_retrabalho,
        observacao=observacao, criado_por=usuario,
    )  # fmt: skip
    registrar(
        usuario=usuario,
        acao="cronometro.iniciar",
        objeto=novo,
        antes={"pausado": anterior.pk if anterior else None},
        depois={"tipo": tipo.slug, "chamado": chamado.pk if chamado else None,
                "projeto": projeto.pk if projeto else None},
    )  # fmt: skip
    return novo, anterior


@transaction.atomic
def parar_cronometro(*, usuario) -> Apontamento:
    aberto = (
        Apontamento.objects.select_for_update()
        .select_related("tipo")
        .filter(usuario=usuario, fim__isnull=True)
        .first()
    )
    if not aberto:
        raise SemCronometroAberto()
    return fechar_apontamento(aberto, fim=timezone.now(), usuario=usuario)


# ---------------------------------------------------------------- lançamento manual


def minutos_do_dia(usuario, dia, *, so_aprovados=True) -> int:
    qs = Apontamento.objects.filter(
        usuario=usuario, fim__isnull=False, inicio__date=dia, tipo__contabiliza_capacidade=True
    )
    if so_aprovados:
        qs = qs.filter(pendente_aprovacao=False)
    return qs.aggregate(m=Sum("minutos"))["m"] or 0


def exige_aprovacao(usuario, inicio: datetime, minutos: int) -> str | None:
    """Motivo da pendência ou None (regra §4)."""
    dia = timezone.localtime(inicio).date()
    if timezone.localdate() - dia > timedelta(days=DIAS_RETROATIVO_EXIGE_APROVACAO):
        return "retroativo"
    if minutos_do_dia(usuario, dia, so_aprovados=False) + minutos > usuario.capacidade_diaria_min:
        return "capacidade"
    return None


@transaction.atomic
def criar_apontamento(
    *, usuario, tipo, inicio: datetime, fim: datetime, chamado=None, projeto=None,
    motivo_retrabalho=None, detalhe_retrabalho: str = "", observacao: str = "",
    lancamento_manual: bool = True,
) -> Apontamento:  # fmt: skip
    _validar_destino(chamado, projeto)
    _validar_causa(tipo, motivo_retrabalho, detalhe_retrabalho)
    if fim <= inicio:
        raise CausaObrigatoria("fim", "O fim deve ser posterior ao início.")
    if conflito := _conflitante(usuario, inicio, fim):
        raise ConflitoDeHoras(conflito)
    minutos = _minutos(inicio, fim)
    motivo_pendencia = exige_aprovacao(usuario, inicio, minutos) if tipo.contabiliza_capacidade else (
        "retroativo" if exige_aprovacao(usuario, inicio, 0) == "retroativo" else None
    )
    try:
        ap = Apontamento.objects.create(
            usuario=usuario, tipo=tipo, chamado=chamado, projeto=projeto, inicio=inicio, fim=fim,
            minutos=minutos, motivo_retrabalho=motivo_retrabalho, detalhe_retrabalho=detalhe_retrabalho,
            observacao=observacao, lancamento_manual=lancamento_manual,
            pendente_aprovacao=motivo_pendencia is not None, criado_por=usuario,
        )  # fmt: skip
    except IntegrityError as e:  # corrida entre a validação e o EXCLUDE
        if "ap_sem_sobreposicao" in str(e) and (c := _conflitante(usuario, inicio, fim)):
            raise ConflitoDeHoras(c) from e
        raise
    registrar(
        usuario=usuario,
        acao="apontamento.criar",
        objeto=ap,
        antes=None,
        depois={"minutos": minutos, "tipo": tipo.slug, "pendente": motivo_pendencia},
    )
    return ap


# ---------------------------------------------------------------- aprovação


def pode_aprovar(aprovador, apontamento: Apontamento) -> bool:
    meus = papeis_de(aprovador)
    if meus & {papeis.GERENTE_TI, papeis.ADMINISTRADOR}:
        return True
    if papeis.GERENTE_SETOR in meus:
        return apontamento.usuario.setor_id == aprovador.setor_id
    return False


@transaction.atomic
def aprovar_apontamento(*, apontamento: Apontamento, aprovador) -> Apontamento:
    apontamento = Apontamento.objects.select_for_update().select_related("usuario").get(pk=apontamento.pk)
    if not apontamento.pendente_aprovacao:
        raise ApontamentoNaoPendente()
    if not pode_aprovar(aprovador, apontamento):
        raise ForaDoEscopoDeAprovacao()
    apontamento.pendente_aprovacao = False
    apontamento.aprovado_por = aprovador
    apontamento.aprovado_em = timezone.now()
    apontamento.save(update_fields=["pendente_aprovacao", "aprovado_por", "aprovado_em", "atualizado_em"])
    registrar(
        usuario=aprovador,
        acao="apontamento.aprovar",
        objeto=apontamento,
        antes={"pendente_aprovacao": True},
        depois={"pendente_aprovacao": False, "aprovado_por": aprovador.pk},
    )
    return apontamento


@transaction.atomic
def recusar_apontamento(*, apontamento: Apontamento, aprovador, motivo: str) -> Apontamento:
    """Recusado sai dos indicadores e fica visível ao autor com o motivo."""
    apontamento = Apontamento.objects.select_for_update().select_related("usuario").get(pk=apontamento.pk)
    if not apontamento.pendente_aprovacao:
        raise ApontamentoNaoPendente()
    if not pode_aprovar(aprovador, apontamento):
        raise ForaDoEscopoDeAprovacao()
    if not motivo or len(motivo.strip()) < 5:
        raise CausaObrigatoria("motivo", "Informe o motivo da recusa.")
    apontamento.pendente_aprovacao = False
    apontamento.recusado_em = timezone.now()
    apontamento.motivo_recusa = motivo.strip()
    apontamento.aprovado_por = aprovador
    apontamento.save(update_fields=["pendente_aprovacao", "recusado_em", "motivo_recusa", "aprovado_por", "atualizado_em"])
    registrar(usuario=aprovador, acao="apontamento.recusar", objeto=apontamento,
              antes={"pendente_aprovacao": True}, depois={"recusado": True, "motivo": apontamento.motivo_recusa})  # fmt: skip
    return apontamento


@transaction.atomic
def decidir_em_lote(*, ids: list[int], aprovador, aprovar: bool, motivo: str = "") -> dict:
    """Modal 'Aprovação de gerente': tudo ou nada — um erro reverte o lote inteiro."""
    feitos = []
    for ap in Apontamento.objects.filter(pk__in=ids).order_by("pk"):
        if aprovar:
            aprovar_apontamento(apontamento=ap, aprovador=aprovador)
        else:
            recusar_apontamento(apontamento=ap, aprovador=aprovador, motivo=motivo)
        feitos.append(ap.pk)
    faltaram = sorted(set(ids) - set(feitos))
    if faltaram:
        raise ApontamentoNaoPendente()
    return {"decididos": feitos, "aprovado": aprovar}
