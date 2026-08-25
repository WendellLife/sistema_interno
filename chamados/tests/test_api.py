import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from chamados import services
from chamados.models import Chamado

pytestmark = pytest.mark.django_db


@pytest.fixture
def chamados(usuarios, categorias):
    """Um chamado de cada setor + um atribuído ao colab_ti."""
    prd = services.abrir_chamado(
        solicitante=usuarios["colab_prd"], titulo="PRD", descricao="d",
        categoria=categorias["suporte"], prioridade="media",
    )  # fmt: skip
    prd2 = services.abrir_chamado(
        solicitante=usuarios["colab_prd2"], titulo="PRD2", descricao="d",
        categoria=categorias["suporte"], prioridade="alta",
    )  # fmt: skip
    man = services.abrir_chamado(
        solicitante=usuarios["colab_man"], titulo="MAN", descricao="d",
        categoria=categorias["dev"], prioridade="critica",
    )  # fmt: skip
    services.atribuir(chamado=man, responsavel=usuarios["colab_ti"], usuario=usuarios["ger_ti"])
    return {"prd": prd, "prd2": prd2, "man": man}


def ids(resposta):
    return {c["id"] for c in resposta.data["results"]}


@pytest.mark.parametrize(
    "papel, esperado",
    [
        ("colab_prd", {"prd"}),                     # só os que abriu
        ("colab_prd2", {"prd2"}),
        ("colab_ti", {"man"}),                      # é responsável
        ("resp_prd", {"prd", "prd2"}),              # o setor
        ("ger_prd", {"prd", "prd2"}),
        ("ger_ti", {"prd", "prd2", "man"}),         # todos
        ("compras", {"prd", "prd2", "man"}),        # leitura de todos
        ("admin", {"prd", "prd2", "man"}),
    ],
)  # fmt: skip
def test_cada_papel_so_enxerga_seu_escopo(api, usuarios, chamados, papel, esperado):
    r = api(usuarios[papel]).get("/api/v1/chamados/")
    assert r.status_code == 200
    assert ids(r) == {chamados[k].id for k in esperado}


def test_fora_do_escopo_nunca_200(api, usuarios, chamados):
    alvo = chamados["man"].id
    assert api(usuarios["colab_prd"]).get(f"/api/v1/chamados/{alvo}/").status_code == 404
    assert api(usuarios["colab_prd"]).patch(f"/api/v1/chamados/{alvo}/", {"titulo": "x"}).status_code == 404
    assert api(usuarios["resp_prd"]).post(
        f"/api/v1/chamados/{alvo}/transicoes/", {"status": "triagem"}
    ).status_code == 404


def test_compras_nao_escreve_em_tarefas(api, usuarios, chamados):
    r = api(usuarios["compras"]).patch(f"/api/v1/chamados/{chamados['prd'].id}/", {"titulo": "x"})
    assert r.status_code == 403


def test_abrir_chamado_como_colaborador(api, usuarios, categorias):
    r = api(usuarios["colab_prd"]).post(
        "/api/v1/chamados/",
        {"titulo": "Etiqueta", "descricao": "Erro", "categoria": categorias["suporte"].id, "prioridade": "alta"},
    )
    assert r.status_code == 201
    assert r.data["setor_origem"]["sigla"] == "PRD"
    assert r.data["numero"].startswith("TI-")
    assert r.data["status"] == "novo"
    assert r.data["minutos_uteis_restantes"] > 0


def test_listagem_traz_resumo_e_filtros(api, usuarios, chamados):
    cli = api(usuarios["ger_ti"])
    r = cli.get("/api/v1/chamados/")
    assert r.data["resumo"]["abertos"] == 3
    assert ids(cli.get("/api/v1/chamados/?prioridade=critica")) == {chamados["man"].id}
    assert ids(cli.get("/api/v1/chamados/?categoria=desenvolvimento")) == {chamados["man"].id}
    assert ids(cli.get("/api/v1/chamados/?busca=PRD2")) == {chamados["prd2"].id}
    assert ids(cli.get(f"/api/v1/chamados/?setor={usuarios['colab_man'].setor_id}")) == {chamados["man"].id}


def test_entrega_bloqueada_retorna_409_estruturado(api, usuarios, chamados):
    cli = api(usuarios["ger_ti"])
    url = f"/api/v1/chamados/{chamados['man'].id}/transicoes/"
    for passo in ("triagem", "fila", "execucao", "testes"):
        assert cli.post(url, {"status": passo}).status_code == 200
    r = cli.post(url, {"status": "entregue"})
    assert r.status_code == 409
    assert r.data["erro"] == "documentacao_incompleta"
    assert "Como foi testado" in r.data["faltando"]


def test_transicao_invalida_409(api, usuarios, chamados):
    r = api(usuarios["ger_ti"]).post(
        f"/api/v1/chamados/{chamados['prd'].id}/transicoes/", {"status": "entregue"}
    )
    assert r.status_code == 409 and r.data["erro"] == "transicao_invalida"


def test_comentario_interno_invisivel_ao_solicitante(api, usuarios, chamados):
    url = f"/api/v1/chamados/{chamados['prd'].id}/comentarios/"
    api(usuarios["ger_ti"]).post(url, {"texto": "nota interna", "interno": True})
    api(usuarios["ger_ti"]).post(url, {"texto": "resposta pública"})
    assert len(api(usuarios["colab_prd"]).get(url).data) == 1
    assert len(api(usuarios["ger_ti"]).get(url).data) == 2
    # solicitante não consegue marcar interno
    api(usuarios["colab_prd"]).post(url, {"texto": "x", "interno": True})
    assert all(not c["interno"] for c in api(usuarios["colab_prd"]).get(url).data)


def test_anexo_e_historico(api, usuarios, chamados):
    cid = chamados["prd"].id
    arquivo = SimpleUploadedFile("nota.txt", b"conteudo", content_type="text/plain")
    r = api(usuarios["colab_prd"]).post(f"/api/v1/chamados/{cid}/anexos/", {"arquivo": arquivo}, format="multipart")
    assert r.status_code == 201 and r.data["tamanho_bytes"] == 8
    h = api(usuarios["colab_prd"]).get(f"/api/v1/chamados/{cid}/historico/")
    assert any("Anexo" in item["texto"] for item in h.data)


def test_patch_prioridade_passa_pelo_servico(api, usuarios, chamados):
    c = chamados["prd"]
    r = api(usuarios["ger_ti"]).patch(f"/api/v1/chamados/{c.id}/", {"prioridade": "critica"})
    assert r.status_code == 200
    novo = Chamado.objects.get(pk=c.id)
    assert novo.prioridade == "critica" and novo.sla_previsto < c.sla_previsto


def test_admin_do_django_nao_edita_status(usuarios):
    from chamados.admin import ChamadoAdmin

    assert "status" in ChamadoAdmin.readonly_fields
