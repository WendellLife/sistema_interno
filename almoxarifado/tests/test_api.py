from decimal import Decimal

import pytest

from almoxarifado import services
from almoxarifado.models import Movimento

pytestmark = pytest.mark.django_db
D = Decimal


def test_saldo_insuficiente_409_estruturado(api, usuarios, itens, setores, cc, estoque_inicial):
    r = api(usuarios["compras"]).post("/api/v1/almoxarifado/movimentos/", {
        "item": itens["parafuso"].id, "setor": setores["MAN"].id, "tipo": "saida",
        "quantidade": "12", "centro_custo": cc["MAN"].id,
    })  # fmt: skip
    assert r.status_code == 409
    assert r.data["erro"] == "saldo_insuficiente" and r.data["item"] == "MRO-4471"


def test_saida_sem_referencia_400(api, usuarios, itens, setores, estoque_inicial):
    r = api(usuarios["compras"]).post("/api/v1/almoxarifado/movimentos/", {
        "item": itens["parafuso"].id, "setor": setores["MAN"].id, "tipo": "saida", "quantidade": "1",
    })  # fmt: skip
    assert r.status_code == 400 and r.data["erro"] == "saida_sem_referencia"


def test_movimento_sem_put_patch_delete(api, usuarios, itens, setores, estoque_inicial):
    m = Movimento.objects.first()
    cli = api(usuarios["admin"])
    url = f"/api/v1/almoxarifado/movimentos/{m.id}/"
    assert cli.get(url).status_code == 200
    assert cli.patch(url, {"quantidade": "1"}).status_code == 405
    assert cli.put(url, {"quantidade": "1"}).status_code == 405
    assert cli.delete(url).status_code == 405


def test_colaborador_solicita_mas_nao_movimenta(api, usuarios, itens, setores, cc, estoque_inicial):
    """Colaborador tem "E" em almoxarifado porque SOLICITA — solicitar não é dar baixa."""
    corpo = {"item": itens["luva"].id, "setor": setores["PRD"].id, "tipo": "saida",
             "quantidade": "1", "centro_custo": cc["PRD"].id}  # fmt: skip
    # nem no próprio setor
    assert api(usuarios["colab_prd"]).post("/api/v1/almoxarifado/movimentos/", corpo).status_code == 403
    # transferência são dois movimentos: mesma recusa
    r = api(usuarios["colab_prd"]).post("/api/v1/almoxarifado/transferencias/", {
        "item": itens["luva"].id, "setor_origem": setores["PRD"].id,
        "setor_destino": setores["MAN"].id, "quantidade": "1", "motivo": "teste",
    }, format="json")  # fmt: skip
    assert r.status_code == 403
    # mas solicitar continua sendo dele
    r = api(usuarios["colab_prd"]).post("/api/v1/almoxarifado/solicitacoes/", {
        "centro_custo": cc["PRD"].id, "itens": [{"item": itens["luva"].id, "quantidade": "1"}],
    }, format="json")  # fmt: skip
    assert r.status_code == 201


def test_responsavel_nao_movimenta_outro_setor(api, usuarios, itens, setores, cc, estoque_inicial):
    """Quem movimenta ainda é limitado ao próprio setor — as duas camadas valem juntas."""
    r = api(usuarios["resp_prd"]).post("/api/v1/almoxarifado/movimentos/", {
        "item": itens["parafuso"].id, "setor": setores["MAN"].id, "tipo": "saida",
        "quantidade": "1", "centro_custo": cc["MAN"].id,
    })  # fmt: skip
    assert r.status_code == 403
    # e não vê os movimentos de MAN
    ids = {m["id"] for m in api(usuarios["resp_prd"]).get("/api/v1/almoxarifado/movimentos/").data["results"]}
    assert all(Movimento.objects.get(pk=i).setor_id == setores["PRD"].id for i in ids)


def test_itens_estoque_e_qrcode(api, usuarios, itens, setores, estoque_inicial):
    cli = api(usuarios["colab_man"])
    r = cli.get("/api/v1/almoxarifado/itens/?busca=parafuso")
    assert r.status_code == 200 and r.data["results"][0]["saldo"] == "10.000"
    r = cli.get("/api/v1/almoxarifado/itens/?abaixo_minimo=true")
    # luva não tem saldo em MAN (0 <= 20) e óleo tem 4 > 2; parafuso 10 > 5
    assert {i["codigo"] for i in r.data["results"]} == {"EPI-0012"}
    r = cli.get("/api/v1/almoxarifado/estoque/")
    assert r.data["setor"] == "MAN" and len(r.data["itens"]) == 2
    r = cli.get("/api/v1/almoxarifado/qrcode/MRO-4471/")
    assert r.status_code == 200 and r.data["saldo"] == D("10.000") and r.data["setor"] == "MAN"
    assert cli.get("/api/v1/almoxarifado/qrcode/NAO-EXISTE/").status_code == 404
    # Compras vê qualquer setor
    r = api(usuarios["compras"]).get(f"/api/v1/almoxarifado/estoque/?setor={setores['PRD'].id}")
    assert r.data["setor"] == "PRD"


def test_solicitacao_pela_api(api, usuarios, itens, setores, cc, estoque_inicial):
    colab = api(usuarios["colab_man"])
    r = colab.post("/api/v1/almoxarifado/solicitacoes/", {
        "centro_custo": cc["MAN"].id, "os_ref": "OS-1", "urgente": True,
        "itens": [{"item": itens["parafuso"].id, "quantidade": "6"}],
    }, format="json")  # fmt: skip
    assert r.status_code == 201 and r.data["status"] == "aberta"
    sid = r.data["id"]
    assert colab.post(f"/api/v1/almoxarifado/solicitacoes/{sid}/aprovar/").status_code == 403
    assert api(usuarios["ger_prd"]).post(f"/api/v1/almoxarifado/solicitacoes/{sid}/aprovar/").status_code == 404
    r = api(usuarios["admin"]).post(f"/api/v1/almoxarifado/solicitacoes/{sid}/aprovar/")
    assert r.status_code == 200 and r.data["status"] == "aprovada"
    r = api(usuarios["admin"]).post(f"/api/v1/almoxarifado/solicitacoes/{sid}/atender/",
                                    {"quantidades": {str(itens["parafuso"].id): "6"}}, format="json")  # fmt: skip
    assert r.status_code == 200 and r.data["status"] == "atendida"
    assert r.data["itens"][0]["pendente"] == "0.000"


def test_nota_transferencia_inventario_pela_api(api, usuarios, itens, setores, estoque_inicial):
    compras = api(usuarios["compras"])
    r = compras.post("/api/v1/almoxarifado/notas-fiscais/", {
        "numero": "555", "fornecedor": "F", "emissao": "2026-08-20", "valor_total": "100.00", "setor": setores["MAN"].id,
        "itens": [{"item": itens["parafuso"].id, "quantidade_recebida": "20", "custo_unitario": "1.50"}],
    }, format="json")  # fmt: skip
    assert r.status_code == 201 and r.data["itens"][0]["quantidade_recebida"] == "20.000"
    # colaborador não lança NF
    r = api(usuarios["colab_man"]).post("/api/v1/almoxarifado/notas-fiscais/", {
        "numero": "556", "fornecedor": "F", "emissao": "2026-08-20", "valor_total": "1", "setor": setores["MAN"].id,
        "itens": [{"item": itens["parafuso"].id, "quantidade_recebida": "1", "custo_unitario": "1"}],
    }, format="json")  # fmt: skip
    assert r.status_code == 403

    r = compras.post("/api/v1/almoxarifado/transferencias/", {
        "item": itens["parafuso"].id, "setor_origem": setores["MAN"].id, "setor_destino": setores["PRD"].id,
        "quantidade": "27", "motivo": "reposição",
    })  # fmt: skip
    assert r.status_code == 201 and r.data["fura_minimo_origem"] is True  # 30 - 27 = 3 < 5

    r = compras.post("/api/v1/almoxarifado/inventarios/", {"setor": setores["MAN"].id})
    assert r.status_code == 201 and len(r.data["contagens"]) == 2
    iid = r.data["id"]
    r = compras.patch(f"/api/v1/almoxarifado/inventarios/{iid}/contagens/",
                      {"contagens": {str(itens["parafuso"].id): "2"}}, format="json")  # fmt: skip
    assert r.status_code == 200 and r.data["registradas"] == 1
    r = compras.post(f"/api/v1/almoxarifado/inventarios/{iid}/fechar/")
    assert r.status_code == 200 and r.data["divergencias"] == 1
    assert r.data["itens_divergentes"][0]["item"]["codigo"] == "MRO-4471"
    assert compras.post(f"/api/v1/almoxarifado/inventarios/{iid}/fechar/").status_code == 409


def test_relatorio_consumo_sem_os(api, usuarios, itens, setores, cc, estoque_inicial):
    u = usuarios["colab_man"]
    geral = services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="saida", quantidade=1,
                                         usuario=u, centro_custo=cc["MAN"])  # fmt: skip
    services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="saida", quantidade=1, usuario=u, os_ref="OS-2")
    r = api(usuarios["compras"]).get("/api/v1/relatorios/consumo/?sem_os=true")
    assert r.status_code == 200 and [m["id"] for m in r.data["movimentos"]] == [geral.id]
    assert r.data["por_setor"][0]["setor"] == "MAN"


def test_gerente_aprova_solicitacao_do_proprio_setor(api, usuarios, itens, setores, cc):
    """Regressão: a matriz dá "V" ao gerente em almoxarifado, e o gate de módulo barrava
    todo POST dele — nenhum gerente aprovava solicitação por nenhum caminho da API."""
    colab = api(usuarios["colab_prd"])
    r = colab.post("/api/v1/almoxarifado/solicitacoes/", {
        "centro_custo": cc["PRD"].id, "os_ref": "OS-7",
        "itens": [{"item": itens["luva"].id, "quantidade": "2"}],
    }, format="json")  # fmt: skip
    assert r.status_code == 201
    sid = r.data["id"]
    r = api(usuarios["ger_prd"]).post(f"/api/v1/almoxarifado/solicitacoes/{sid}/aprovar/")
    assert r.status_code == 200 and r.data["status"] == "aprovada"


def test_busca_encontra_item_e_solicitacao(api, usuarios, itens, cc):
    sol = services.criar_solicitacao(solicitante=usuarios["colab_man"], centro_custo=cc["MAN"],
                                     itens=[{"item": itens["luva"], "quantidade": 1}])  # fmt: skip
    r = api(usuarios["ger_ti"]).get("/api/v1/busca/?q=nitrilica")
    assert any(x["tipo"] == "item" and x["id"] == itens["luva"].id for x in r.data["resultados"])
    r = api(usuarios["ger_ti"]).get(f"/api/v1/busca/?q={sol.numero}")
    assert any(x["tipo"] == "solicitacao" and x["id"] == sol.id for x in r.data["resultados"])
