from datetime import timedelta

import pytest
from django.utils import timezone

from apontamentos import services

pytestmark = pytest.mark.django_db


def hoje_as(h):
    return timezone.localtime(timezone.now()).replace(hour=h, minute=0, second=0, microsecond=0)


def test_cronometro_fluxo_completo(api, usuarios, tipos, chamado):
    cli = api(usuarios["colab_ti"])
    assert cli.get("/api/v1/cronometro/").data is None
    r = cli.post("/api/v1/cronometro/iniciar/", {"tipo": tipos["desenvolvimento"].id, "chamado": chamado.id})
    assert r.status_code == 201 and r.data["pausado"] is None
    r = cli.post("/api/v1/cronometro/iniciar/", {"tipo": tipos["testes"].id, "chamado": chamado.id})
    assert r.status_code == 201
    assert r.data["pausado"]["tipo"] == "Desenvolvimento" and "minutos" in r.data["pausado"]
    assert cli.get("/api/v1/cronometro/").data["tipo"]["slug"] == "testes"
    r = cli.post("/api/v1/cronometro/parar/")
    assert r.status_code == 200 and r.data["fim"] is not None
    assert cli.post("/api/v1/cronometro/parar/").status_code == 404


def test_retrabalho_sem_motivo_400_pela_api(api, usuarios, tipos, motivos, chamado):
    cli = api(usuarios["colab_ti"])
    r = cli.post("/api/v1/cronometro/iniciar/", {"tipo": tipos["retrabalho"].id, "chamado": chamado.id})
    assert r.status_code == 400 and r.data == {"motivo_retrabalho": ["Obrigatório para retrabalho."]}
    r = cli.post("/api/v1/cronometro/iniciar/", {
        "tipo": tipos["retrabalho"].id, "chamado": chamado.id,
        "motivo_retrabalho": motivos[0].id, "detalhe_retrabalho": "Requisito incompleto do solicitante",
    })  # fmt: skip
    assert r.status_code == 201 and r.data["apontamento"]["motivo_retrabalho"]["id"] == motivos[0].id


def test_lancamento_manual_conflito_400(api, usuarios, tipos, chamado):
    cli = api(usuarios["colab_ti"])
    base = {"tipo": tipos["analise"].id, "chamado": chamado.id}
    r = cli.post("/api/v1/apontamentos/", {**base, "inicio": hoje_as(8), "fim": hoje_as(12)})
    assert r.status_code == 201 and r.data["minutos"] == 240 and r.data["lancamento_manual"] is True
    r = cli.post("/api/v1/apontamentos/", {**base, "inicio": hoje_as(11), "fim": hoje_as(13)})
    assert r.status_code == 400 and r.data["erro"] == "conflito_horas"
    assert r.data["mensagem"].startswith("Conflita com apontamento de Análise")


def test_escopo_por_papel_em_apontamentos(api, usuarios, tipos, chamado):
    services.criar_apontamento(usuario=usuarios["colab_ti"], tipo=tipos["analise"], chamado=chamado,
                               inicio=hoje_as(8), fim=hoje_as(9))  # fmt: skip
    services.criar_apontamento(usuario=usuarios["colab_prd"], tipo=tipos["analise"], chamado=chamado,
                               inicio=hoje_as(8), fim=hoje_as(9))  # fmt: skip

    def ids(u):
        return {a["usuario"]["id"] for a in api(u).get("/api/v1/apontamentos/").data["results"]}

    assert ids(usuarios["colab_ti"]) == {usuarios["colab_ti"].id}
    assert ids(usuarios["colab_prd2"]) == set()
    assert ids(usuarios["resp_prd"]) == {usuarios["colab_prd"].id}
    assert ids(usuarios["ger_ti"]) == {usuarios["colab_ti"].id, usuarios["colab_prd"].id}
    # Compras não tem acesso ao módulo
    assert api(usuarios["compras"]).get("/api/v1/apontamentos/").status_code == 403


def test_pendentes_e_aprovar(api, usuarios, tipos, chamado):
    ini = hoje_as(8) - timedelta(days=10)
    ap = services.criar_apontamento(usuario=usuarios["colab_prd"], tipo=tipos["analise"], chamado=chamado,
                                    inicio=ini, fim=ini + timedelta(hours=1))  # fmt: skip
    assert api(usuarios["colab_prd"]).get("/api/v1/apontamentos/pendentes/").status_code == 403
    assert [a["id"] for a in api(usuarios["ger_prd"]).get("/api/v1/apontamentos/pendentes/").data] == [ap.id]
    r = api(usuarios["ger_prd"]).post(f"/api/v1/apontamentos/{ap.id}/aprovar/")
    assert r.status_code == 200 and r.data["pendente_aprovacao"] is False


def test_relatorios(api, usuarios, tipos, motivos, chamado):
    services.criar_apontamento(usuario=usuarios["colab_ti"], tipo=tipos["desenvolvimento"], chamado=chamado,
                               inicio=hoje_as(8), fim=hoje_as(11))  # fmt: skip
    services.criar_apontamento(usuario=usuarios["colab_ti"], tipo=tipos["retrabalho"], chamado=chamado,
                               inicio=hoje_as(11), fim=hoje_as(12), motivo_retrabalho=motivos[1],
                               detalhe_retrabalho="Erro de análise identificado em teste")  # fmt: skip
    r = api(usuarios["ger_ti"]).get("/api/v1/relatorios/horas/")
    assert r.status_code == 200 and r.data["total_min"] == 240
    assert r.data["por_chamado"][0]["numero"] == chamado.numero
    r = api(usuarios["ger_ti"]).get("/api/v1/relatorios/retrabalho/")
    assert r.data["percentual"] == 25.0 and r.data["por_motivo"][0]["motivo"] == motivos[1].nome
    # colaborador de outro setor vê zero
    assert api(usuarios["colab_prd"]).get("/api/v1/relatorios/horas/").data["total_min"] == 0
