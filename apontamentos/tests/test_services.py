import threading
from datetime import datetime, timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apontamentos import selectors, services
from apontamentos.exceptions import (
    ApontamentoNaoPendente,
    CausaObrigatoria,
    ConflitoDeHoras,
    ForaDoEscopoDeAprovacao,
    SemCronometroAberto,
)
from apontamentos.models import Apontamento
from core.calendario import FUSO
from core.models import Auditoria

pytestmark = pytest.mark.django_db


def hoje_as(h, m=0):
    return timezone.localtime(timezone.now()).replace(hour=h, minute=m, second=0, microsecond=0)


# ---------------------------------------------------------------- §1 retrabalho


def test_retrabalho_sem_motivo_e_recusado(usuarios, tipos, motivos, chamado):
    with pytest.raises(CausaObrigatoria):
        services.iniciar_cronometro(usuario=usuarios["colab_ti"], tipo=tipos["retrabalho"], chamado=chamado)
    with pytest.raises(CausaObrigatoria) as e:
        services.iniciar_cronometro(
            usuario=usuarios["colab_ti"], tipo=tipos["retrabalho"], chamado=chamado,
            motivo_retrabalho=motivos[0], detalhe_retrabalho="curto",
        )  # fmt: skip
    assert e.value.campo == "detalhe_retrabalho"
    novo, _ = services.iniciar_cronometro(
        usuario=usuarios["colab_ti"], tipo=tipos["retrabalho"], chamado=chamado,
        motivo_retrabalho=motivos[0], detalhe_retrabalho="Requisito veio incompleto do solicitante",
    )  # fmt: skip
    assert novo.motivo_retrabalho_id == motivos[0].id and novo.tipo_exige_causa is True


def test_banco_recusa_update_que_limpa_motivo(usuarios, tipos, motivos, chamado):
    novo, _ = services.iniciar_cronometro(
        usuario=usuarios["colab_ti"], tipo=tipos["retrabalho"], chamado=chamado,
        motivo_retrabalho=motivos[0], detalhe_retrabalho="Requisito veio incompleto do solicitante",
    )  # fmt: skip
    with pytest.raises(IntegrityError), transaction.atomic():
        Apontamento.objects.filter(pk=novo.pk).update(motivo_retrabalho=None)


# ---------------------------------------------------------------- §2 cronômetro único


def test_iniciar_fecha_o_anterior_na_mesma_transacao(usuarios, tipos, chamado):
    u = usuarios["colab_ti"]
    a, pausado = services.iniciar_cronometro(usuario=u, tipo=tipos["desenvolvimento"], chamado=chamado)
    assert pausado is None
    Apontamento.objects.filter(pk=a.pk).update(inicio=timezone.now() - timedelta(minutes=72))
    b, pausado = services.iniciar_cronometro(usuario=u, tipo=tipos["testes"], chamado=chamado)
    assert pausado.pk == a.pk and pausado.minutos == 72 and pausado.fim is not None
    assert Apontamento.objects.filter(usuario=u, fim__isnull=True).count() == 1
    assert services.cronometro_aberto(u).pk == b.pk


def test_parar_sem_cronometro(usuarios):
    with pytest.raises(SemCronometroAberto):
        services.parar_cronometro(usuario=usuarios["colab_ti"])


def test_destino_obrigatorio(usuarios, tipos):
    with pytest.raises(CausaObrigatoria):
        services.iniciar_cronometro(usuario=usuarios["colab_ti"], tipo=tipos["analise"])


@pytest.mark.django_db(transaction=True)
def test_cronometros_concorrentes_nao_criam_dois_abertos(usuarios, tipos, chamado):
    u = usuarios["colab_ti"]
    erros = []

    def worker():
        try:
            services.iniciar_cronometro(usuario=u, tipo=tipos["analise"], chamado=chamado)
        except Exception as e:  # noqa: BLE001
            erros.append(e)
        finally:
            connection.close()

    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert Apontamento.objects.filter(usuario=u, fim__isnull=True).count() == 1


# ---------------------------------------------------------------- §3 não sobreposição


def test_lancamentos_sobrepostos_sao_recusados_com_mensagem(usuarios, tipos, chamado):
    u = usuarios["colab_ti"]
    services.criar_apontamento(
        usuario=u, tipo=tipos["analise"], chamado=chamado, inicio=hoje_as(8), fim=hoje_as(12)
    )
    with pytest.raises(ConflitoDeHoras) as e:
        services.criar_apontamento(
            usuario=u, tipo=tipos["testes"], chamado=chamado, inicio=hoje_as(11), fim=hoje_as(13)
        )
    assert str(e.value) == "Conflita com apontamento de Análise (08:00–12:00)"
    # encostado (12:00–13:00) é permitido
    ap = services.criar_apontamento(
        usuario=u, tipo=tipos["testes"], chamado=chamado, inicio=hoje_as(12), fim=hoje_as(13)
    )
    assert ap.minutos == 60


def test_banco_recusa_sobreposicao_direta(usuarios, tipos, chamado):
    u = usuarios["colab_ti"]
    services.criar_apontamento(
        usuario=u, tipo=tipos["analise"], chamado=chamado, inicio=hoje_as(8), fim=hoje_as(12)
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Apontamento.objects.create(
            usuario=u, tipo=tipos["analise"], chamado=chamado, inicio=hoje_as(9), fim=hoje_as(10), minutos=60
        )


def test_usuarios_diferentes_podem_sobrepor(usuarios, tipos, chamado):
    for u in (usuarios["colab_ti"], usuarios["ger_ti"]):
        services.criar_apontamento(
            usuario=u, tipo=tipos["analise"], chamado=chamado, inicio=hoje_as(8), fim=hoje_as(12)
        )
    assert Apontamento.objects.count() == 2


# ---------------------------------------------------------------- §4 capacidade / retroativo


def test_9h_no_dia_fica_pendente_e_fora_do_relatorio(usuarios, tipos, chamado):
    u = usuarios["colab_ti"]
    ok = services.criar_apontamento(
        usuario=u, tipo=tipos["desenvolvimento"], chamado=chamado, inicio=hoje_as(8), fim=hoje_as(12)
    )
    assert ok.pendente_aprovacao is False
    extra = services.criar_apontamento(
        usuario=u, tipo=tipos["desenvolvimento"], chamado=chamado, inicio=hoje_as(13), fim=hoje_as(18)
    )
    assert extra.pendente_aprovacao is True  # 4h + 5h = 9h > 8h
    total = selectors.percentual_retrabalho(selectors.validos(usuario=u))["total_min"]
    assert total == 240
    services.aprovar_apontamento(apontamento=extra, aprovador=usuarios["ger_ti"])
    total = selectors.percentual_retrabalho(selectors.validos(usuario=u))["total_min"]
    assert total == 540


def test_espera_de_terceiro_nao_conta_capacidade(usuarios, tipos, chamado):
    u = usuarios["colab_ti"]
    ap = services.criar_apontamento(
        usuario=u, tipo=tipos["espera_terceiro"], chamado=chamado, inicio=hoje_as(8), fim=hoje_as(18)
    )
    assert ap.pendente_aprovacao is False


def test_retroativo_mais_de_7_dias_exige_aprovacao(usuarios, tipos, chamado):
    inicio = hoje_as(8) - timedelta(days=10)
    ap = services.criar_apontamento(
        usuario=usuarios["colab_ti"], tipo=tipos["analise"], chamado=chamado,
        inicio=inicio, fim=inicio + timedelta(hours=1),
    )  # fmt: skip
    assert ap.pendente_aprovacao is True


# ---------------------------------------------------------------- aprovação


def test_aprovacao_escopo_e_auditoria(usuarios, tipos, chamado):
    inicio = hoje_as(8) - timedelta(days=10)
    ap = services.criar_apontamento(
        usuario=usuarios["colab_ti"], tipo=tipos["analise"], chamado=chamado,
        inicio=inicio, fim=inicio + timedelta(hours=1),
    )  # fmt: skip
    with pytest.raises(ForaDoEscopoDeAprovacao):  # gerente de PRD não aprova gente de TI
        services.aprovar_apontamento(apontamento=ap, aprovador=usuarios["ger_prd"])
    ap = services.aprovar_apontamento(apontamento=ap, aprovador=usuarios["ger_ti"])
    assert ap.aprovado_por == usuarios["ger_ti"] and ap.aprovado_em
    assert Auditoria.objects.filter(acao="apontamento.aprovar", objeto_id=str(ap.pk)).exists()
    with pytest.raises(ApontamentoNaoPendente):
        services.aprovar_apontamento(apontamento=ap, aprovador=usuarios["ger_ti"])


# ---------------------------------------------------------------- relatórios


def test_relatorio_retrabalho_por_motivo(usuarios, tipos, motivos, chamado):
    u = usuarios["colab_ti"]
    services.criar_apontamento(
        usuario=u, tipo=tipos["desenvolvimento"], chamado=chamado, inicio=hoje_as(8), fim=hoje_as(11)
    )
    services.criar_apontamento(
        usuario=u, tipo=tipos["retrabalho"], chamado=chamado, inicio=hoje_as(11), fim=hoje_as(12),
        motivo_retrabalho=motivos[0], detalhe_retrabalho="Requisito veio incompleto do solicitante",
    )  # fmt: skip
    r = selectors.percentual_retrabalho(selectors.validos())
    assert r == {"total_min": 240, "retrabalho_min": 60, "percentual": 25.0}
    por_motivo = selectors.retrabalho_por_motivo(selectors.validos())
    assert por_motivo[0]["motivo"] == motivos[0].nome and por_motivo[0]["minutos"] == 60
    por_origem = selectors.retrabalho_por_origem(selectors.validos())
    assert por_origem[0]["setor"] == "PRD"


def test_minutos_inteiros_nunca_float(usuarios, tipos, chamado):
    ini = datetime(2026, 8, 24, 8, 0, 30, tzinfo=FUSO)
    ap = services.criar_apontamento(
        usuario=usuarios["colab_ti"], tipo=tipos["analise"], chamado=chamado,
        inicio=ini, fim=ini + timedelta(minutes=90, seconds=50),
    )  # fmt: skip
    assert isinstance(ap.minutos, int) and ap.minutos == 90
