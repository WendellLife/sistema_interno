from datetime import datetime

import pytest
from django.utils import timezone

from chamados import services
from chamados.exceptions import (
    DocumentacaoIncompleta,
    JustificativaObrigatoria,
    SemPermissaoParaAcao,
    TransicaoInvalida,
)
from chamados.models import Chamado, HistoricoChamado
from core.calendario import FUSO
from core.models import Auditoria
from documentacao.services import publicar_secao

pytestmark = pytest.mark.django_db


def abrir(usuarios, categorias, cat="suporte", prio="media", **kw):
    return services.abrir_chamado(
        solicitante=usuarios["colab_prd"],
        titulo="Teste",
        descricao="Descrição",
        categoria=categorias[cat],
        prioridade=prio,
        **kw,
    )


def levar_ate_testes(chamado, usuario):
    for passo in ("triagem", "fila", "execucao", "testes"):
        chamado = services.transicionar(chamado=chamado, para=passo, usuario=usuario)
    return chamado


def test_abrir_gera_numero_sla_historico_e_auditoria(usuarios, categorias):
    c = abrir(usuarios, categorias)
    assert c.numero.startswith(f"TI-{timezone.localdate().year}-")
    assert c.setor_origem == usuarios["colab_prd"].setor
    assert c.sla_previsto is not None and c.sla_previsto > c.criado_em
    assert HistoricoChamado.objects.filter(chamado=c).count() == 1
    assert Auditoria.objects.filter(acao="chamado.abrir", objeto_id=str(c.id)).exists()


def test_sla_critica_sexta_16h(usuarios, categorias):
    sexta = datetime(2026, 8, 21, 16, 0, tzinfo=FUSO)
    c = abrir(usuarios, categorias, prio="critica")
    Chamado.objects.filter(pk=c.pk).update(criado_em=sexta)
    c.refresh_from_db()
    assert services.calcular_sla(c).astimezone(FUSO) == datetime(2026, 8, 24, 11, 0, tzinfo=FUSO)


def test_maquina_de_estados_recusa_pulo(usuarios, categorias):
    c = abrir(usuarios, categorias)
    with pytest.raises(TransicaoInvalida):
        services.transicionar(chamado=c, para="execucao", usuario=usuarios["ger_ti"])


def test_fluxo_completo_suporte_sem_documentacao_entrega(usuarios, categorias):
    c = levar_ate_testes(abrir(usuarios, categorias), usuarios["ger_ti"])
    c = services.entregar_chamado(chamado=c, usuario=usuarios["ger_ti"])
    assert c.status == "entregue"
    assert c.entregue_em is not None
    assert c.sla_cumprido is True
    a = Auditoria.objects.get(acao="chamado.entregue", objeto_id=str(c.id))
    assert a.antes == {"status": "testes"} and a.depois["status"] == "entregue"


def test_desenvolvimento_sem_documentacao_nao_entrega(usuarios, categorias):
    c = levar_ate_testes(abrir(usuarios, categorias, cat="dev"), usuarios["ger_ti"])
    with pytest.raises(DocumentacaoIncompleta) as exc:
        services.entregar_chamado(chamado=c, usuario=usuarios["ger_ti"])
    assert exc.value.extras["faltando"] == [
        "Contexto e problema", "Regra de negócio", "Solução aplicada", "Como foi testado",
    ]  # fmt: skip
    c.refresh_from_db()
    assert c.status == "testes"


def test_desenvolvimento_com_4_secoes_publicadas_entrega(usuarios, categorias):
    c = levar_ate_testes(abrir(usuarios, categorias, cat="dev"), usuarios["ger_ti"])
    for secao in ("contexto", "regra", "solucao"):
        publicar_secao(chamado=c, secao=secao, conteudo="ok", autor=usuarios["colab_ti"])
    ok, faltando = services.pode_entregar(c)
    assert not ok and faltando == ["Como foi testado"]
    publicar_secao(chamado=c, secao="teste", conteudo="testado", autor=usuarios["colab_ti"])
    assert services.entregar_chamado(chamado=c, usuario=usuarios["ger_ti"]).status == "entregue"


def test_alterar_prioridade_recalcula_sla_da_abertura(usuarios, categorias):
    c = abrir(usuarios, categorias, prio="baixa")
    sla_baixa = c.sla_previsto
    c = services.alterar_prioridade(chamado=c, prioridade="critica", usuario=usuarios["ger_ti"])
    assert c.sla_previsto < sla_baixa
    assert HistoricoChamado.objects.filter(chamado=c, texto__startswith="Prioridade").exists()


def test_cancelar_exige_papel_e_justificativa(usuarios, categorias):
    c = abrir(usuarios, categorias)
    with pytest.raises(SemPermissaoParaAcao):
        services.cancelar(chamado=c, usuario=usuarios["colab_prd"], justificativa="motivo válido")
    with pytest.raises(JustificativaObrigatoria):
        services.cancelar(chamado=c, usuario=usuarios["resp_prd"], justificativa="")
    c = services.cancelar(chamado=c, usuario=usuarios["resp_prd"], justificativa="Duplicado")
    assert c.status == "cancelado"
    with pytest.raises(TransicaoInvalida):
        services.cancelar(chamado=c, usuario=usuarios["resp_prd"], justificativa="de novo")


def test_marcar_slas_vencidos_nao_fecha(usuarios, categorias):
    c = abrir(usuarios, categorias)
    Chamado.objects.filter(pk=c.pk).update(sla_previsto=timezone.now() - timezone.timedelta(hours=1))
    assert services.marcar_slas_vencidos() == 1
    c.refresh_from_db()
    assert c.sla_cumprido is False and c.status == "novo"
