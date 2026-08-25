import hashlib
import hmac
import json
from unittest import mock

import pytest
from rest_framework.test import APIClient

from almoxarifado.models import Item, Solicitacao
from chamados import services as cham
from core.models import CentroCusto
from integracoes.models import ChaveIdempotencia, EventoIntegracao, SistemaExterno, Webhook
from integracoes.tasks import entregar_evento

pytestmark = pytest.mark.django_db


@pytest.fixture
def sistema(usuarios):
    s = SistemaExterno(nome="ERP", slug="erp", usuario_tecnico=usuarios["compras"],
                       escopos=["almoxarifado:escrever", "almoxarifado:ler", "eventos:ler"])  # fmt: skip
    chave = s.gerar_chave()
    s.save()
    s.chave_clara = chave
    return s


@pytest.fixture
def cli(sistema):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Api-Key {sistema.chave_clara}")
    return c


@pytest.fixture
def item(setores):
    return Item.objects.create(codigo="MRO-1", descricao="Parafuso", unidade="UN", setor_dono=setores["MAN"], codigo_sankhya="SK-100")


@pytest.fixture
def cc(setores):
    return CentroCusto.objects.create(codigo="2001", descricao="Manutenção", setor=setores["MAN"])


def test_chave_guardada_como_hash_e_autentica(sistema, cli):
    assert sistema.chave_hash != sistema.chave_clara and sistema.prefixo_chave == sistema.chave_clara[:8]
    r = cli.get("/api/v1/integracoes/estoque/")
    assert r.status_code == 200
    sistema.refresh_from_db()
    assert sistema.ultimo_uso is not None
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION="Api-Key li_invalida")
    assert c.get("/api/v1/integracoes/estoque/").status_code == 401


def test_escopo_e_ip(sistema, cli, usuarios):
    # sem escopo de chamados
    r = cli.post("/api/v1/integracoes/chamados/", {"solicitante": {"matricula": "colab_prd"}, "titulo": "t",
                                                   "descricao": "d", "categoria": "suporte"}, format="json")  # fmt: skip
    assert r.status_code == 403
    sistema.ips_permitidos = ["10.0.0.9"]
    sistema.save()
    assert cli.get("/api/v1/integracoes/estoque/").status_code == 401
    assert cli.get("/api/v1/integracoes/estoque/", REMOTE_ADDR="10.0.0.9").status_code == 200


def test_solicitacao_externa_e_idempotencia(cli, usuarios, item, cc, sistema):
    corpo = {"solicitante": {"matricula": "colab_man"}, "os_ref": "OS-1", "origem": "whatsapp",
             "itens": [{"codigo_sankhya": "SK-100", "quantidade": "3"}]}  # fmt: skip
    r1 = cli.post("/api/v1/integracoes/solicitacoes/", corpo, format="json", HTTP_IDEMPOTENCY_KEY="abc-1")
    assert r1.status_code == 201 and r1.data["origem"] == "whatsapp" and r1.data["numero"].startswith("SOL-")
    assert r1.data["centro_custo"] == cc.id  # padrão do setor
    r2 = cli.post("/api/v1/integracoes/solicitacoes/", corpo, format="json", HTTP_IDEMPOTENCY_KEY="abc-1")
    assert r2.status_code == 201 and r2.data == r1.data and r2["Idempotent-Replayed"] == "true"
    assert Solicitacao.objects.count() == 1 and ChaveIdempotencia.objects.count() == 1
    # sem chave → cria outra
    r3 = cli.post("/api/v1/integracoes/solicitacoes/", corpo, format="json")
    assert r3.status_code == 201 and Solicitacao.objects.count() == 2
    # solicitante desconhecido
    r = cli.post("/api/v1/integracoes/solicitacoes/", {**corpo, "solicitante": {"email": "x@y.z"}}, format="json")
    assert r.status_code == 400


def test_sync_de_itens(cli, setores, item):
    r = cli.post("/api/v1/integracoes/itens/sync/", [
        {"codigo_sankhya": "SK-100", "descricao": "Parafuso M8", "custo_unitario": "1.20"},
        {"codigo_sankhya": "SK-200", "codigo": "MRO-2", "descricao": "Porca", "unidade": "UN", "setor_dono": "MAN"},
    ], format="json")  # fmt: skip
    assert r.status_code == 200 and r.data == {"criados": 1, "atualizados": 1}
    item.refresh_from_db()
    assert item.descricao == "Parafuso M8" and str(item.custo_unitario) == "1.20"
    r = cli.post("/api/v1/integracoes/itens/sync/", [{"codigo_sankhya": "SK-300", "descricao": "x"}], format="json")
    assert r.status_code == 400 and set(r.data["faltando"]) == {"codigo", "unidade", "setor_dono"}


def test_outbox_webhook_hmac_e_polling(sistema, cli, usuarios, categorias, django_capture_on_commit_callbacks):
    wh = Webhook.objects.create(sistema=sistema, url="https://erp.local/hook", segredo="s3gr3d0",
                                eventos=["chamado.*", "estoque.saida"], criado_por=usuarios["admin"])  # fmt: skip
    assert wh.assina("chamado.abrir") and wh.assina("estoque.saida") and not wh.assina("estoque.entrada")

    enviado = {}

    def fake_post(url, data, timeout, headers):
        enviado.update(url=url, data=data, headers=headers)
        return mock.Mock(raise_for_status=lambda: None)

    with mock.patch("requests.post", side_effect=fake_post), django_capture_on_commit_callbacks(execute=True):
        c = cham.abrir_chamado(solicitante=usuarios["colab_prd"], titulo="Via API", descricao="d",
                               categoria=categorias["suporte"], prioridade="alta")  # fmt: skip
    ev = EventoIntegracao.objects.get(webhook=wh, acao="chamado.abrir")
    assert ev.status == "entregue" and ev.carga["objeto"] == {"tipo": "chamados.chamado", "id": str(c.id)}
    assert enviado["url"] == wh.url and enviado["headers"]["X-Evento"] == "chamado.abrir"
    esperado = hmac.new(b"s3gr3d0", enviado["data"], hashlib.sha256).hexdigest()
    assert enviado["headers"]["X-Assinatura"] == esperado
    assert json.loads(enviado["data"])["depois"]["numero"] == c.numero

    r = cli.get("/api/v1/integracoes/eventos/")
    assert r.status_code == 200 and [e["acao"] for e in r.data] == ["chamado.abrir"]
    assert cli.get(f"/api/v1/integracoes/eventos/?desde={ev.id}").data == []


def test_entrega_falha_agenda_retentativa(sistema, usuarios, categorias):
    wh = Webhook.objects.create(sistema=sistema, url="https://erp.local/hook", segredo="x", eventos=["chamado.abrir"])
    with mock.patch("requests.post", side_effect=ConnectionError("recusado")):
        c = cham.abrir_chamado(solicitante=usuarios["colab_prd"], titulo="t", descricao="d",
                               categoria=categorias["suporte"], prioridade="alta")  # fmt: skip
        ev = EventoIntegracao.objects.get(webhook=wh)
        entregar_evento(ev.pk)
    ev.refresh_from_db()
    assert ev.status == "pendente" and ev.tentativas == 1 and ev.proxima_tentativa and "recusado" in ev.ultimo_erro
    assert c.pk


def test_admin_cria_sistema_e_ve_chave_uma_vez(api, usuarios):
    adm = api(usuarios["admin"])
    r = adm.post("/api/v1/integracoes/sistemas/", {"nome": "WhatsApp Bot", "slug": "whatsapp", "escopos": ["almoxarifado:escrever"],
                                                    "usuario_tecnico": usuarios["compras"].id}, format="json")  # fmt: skip
    assert r.status_code == 201 and r.data["chave"].startswith("li_")
    sid = r.data["id"]
    assert "chave" not in adm.get(f"/api/v1/integracoes/sistemas/{sid}/").data
    r2 = adm.post(f"/api/v1/integracoes/sistemas/{sid}/rotacionar-chave/")
    assert r2.status_code == 200 and r2.data["chave"] != r.data["chave"]
    assert api(usuarios["ger_ti"]).get("/api/v1/integracoes/sistemas/").status_code == 403


def test_schema_e_health(api, usuarios):
    assert api(usuarios["admin"]).get("/api/schema/").status_code == 200
    r = APIClient().get("/health/")
    assert r.status_code == 200 and r.json()["db"] is True
