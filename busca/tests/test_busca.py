import pytest

from busca.services import buscar
from chamados import services as chamados_services
from projetos.models import Projeto

pytestmark = pytest.mark.django_db


@pytest.fixture
def dados(usuarios, categorias, setores):
    c1 = chamados_services.abrir_chamado(
        solicitante=usuarios["colab_prd"], titulo="Erro ao gerar etiqueta de expedição",
        descricao="A impressora zebra não responde", categoria=categorias["suporte"], prioridade="alta",
    )  # fmt: skip
    c2 = chamados_services.abrir_chamado(
        solicitante=usuarios["colab_man"], titulo="Relatório de horas extras",
        descricao="por centro de custo", categoria=categorias["suporte"], prioridade="media",
    )  # fmt: skip
    p = Projeto.objects.create(
        nome="Dashboard de OEE para manutenção", setor_solicitante=setores["MAN"],
        patrocinador=usuarios["colab_man"], responsavel=usuarios["colab_ti"],
    )  # fmt: skip
    return c1, c2, p


def tipos_ids(res):
    return {(r["tipo"], r["id"]) for r in res}


def test_full_text_e_trigram(usuarios, dados):
    c1, c2, p = dados
    ger = usuarios["ger_ti"]
    assert tipos_ids(buscar(user=ger, q="etiqueta")) == {("chamado", c1.id)}
    assert tipos_ids(buscar(user=ger, q="etiquetas expedicao")) == {("chamado", c1.id)}  # stemming pt
    assert tipos_ids(buscar(user=ger, q="impressora")) == {("chamado", c1.id)}  # descrição
    assert tipos_ids(buscar(user=ger, q=c1.numero[-4:])) >= {("chamado", c1.id)}  # trigram no número
    assert tipos_ids(buscar(user=ger, q="OEE")) == {("projeto", p.id)}
    assert buscar(user=ger, q="x") == []


def test_escopo_por_papel(usuarios, dados):
    c1, c2, p = dados
    assert tipos_ids(buscar(user=usuarios["colab_prd"], q="etiqueta")) == {("chamado", c1.id)}
    assert buscar(user=usuarios["colab_prd"], q="horas extras") == []
    assert buscar(user=usuarios["colab_prd"], q="OEE") == []  # colaborador não vê projetos
    assert tipos_ids(buscar(user=usuarios["resp_prd"], q="etiqueta")) == {("chamado", c1.id)}
    assert buscar(user=usuarios["resp_prd"], q="OEE") == []  # projeto é de MAN


def test_endpoint_e_formato(api, usuarios, dados):
    r = api(usuarios["ger_ti"]).get("/api/v1/busca/?q=etiqueta")
    assert r.status_code == 200
    item = r.data["resultados"][0]
    assert set(item) == {"tipo", "id", "titulo", "subtitulo", "url"}
    assert item["url"].startswith("/tarefas/")
