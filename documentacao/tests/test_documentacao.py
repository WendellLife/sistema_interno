import pytest
from django.db import IntegrityError, transaction

from chamados import services as chamados_services
from chamados.exceptions import DocumentacaoIncompleta
from documentacao import selectors, services
from documentacao.exceptions import ConteudoVazio, DestinoInvalido, VersaoJaPublicada
from documentacao.models import Documento, VersaoDocumento

pytestmark = pytest.mark.django_db


@pytest.fixture
def chamado_dev(usuarios, categorias):
    return chamados_services.abrir_chamado(
        solicitante=usuarios["colab_prd"], titulo="Dev", descricao="d",
        categoria=categorias["dev"], prioridade="media",
    )  # fmt: skip


@pytest.fixture
def chamado_sup(usuarios, categorias):
    return chamados_services.abrir_chamado(
        solicitante=usuarios["colab_man"], titulo="Sup", descricao="d",
        categoria=categorias["suporte"], prioridade="media",
    )  # fmt: skip


def ate_testes(c, u):
    for p in ("triagem", "fila", "execucao", "testes"):
        c = chamados_services.transicionar(chamado=c, para=p, usuario=u)
    return c


def test_abrir_chamado_cria_6_secoes_com_obrigatoriedade(chamado_dev, chamado_sup):
    docs = Documento.objects.filter(chamado=chamado_dev)
    assert docs.count() == 6
    assert set(docs.filter(obrigatorio=True).values_list("secao", flat=True)) == {
        "contexto", "regra", "solucao", "teste",
    }  # fmt: skip
    assert not Documento.objects.filter(chamado=chamado_sup, obrigatorio=True).exists()


def test_versoes_sao_append_only(usuarios, chamado_dev):
    doc = Documento.objects.get(chamado=chamado_dev, secao="contexto")
    v1 = services.criar_rascunho(documento=doc, conteudo="primeira", autor=usuarios["colab_ti"])
    v2 = services.criar_rascunho(documento=doc, conteudo="segunda", autor=usuarios["colab_ti"])
    assert (v1.numero, v2.numero) == (1, 2)
    assert selectors.status_documento(Documento.objects.get(pk=doc.pk)) == "rascunho"
    with pytest.raises(IntegrityError), transaction.atomic():
        VersaoDocumento.objects.create(documento=doc, numero=2, conteudo="x", autor=usuarios["colab_ti"])
    with pytest.raises(ConteudoVazio):
        services.criar_rascunho(documento=doc, conteudo="   ", autor=usuarios["colab_ti"])


def test_publicar_define_versao_atual_e_nao_repete(usuarios, chamado_dev):
    doc = Documento.objects.get(chamado=chamado_dev, secao="regra")
    v1 = services.criar_rascunho(documento=doc, conteudo="v1", autor=usuarios["colab_ti"])
    v2 = services.criar_rascunho(documento=doc, conteudo="v2", autor=usuarios["colab_ti"])
    services.publicar_versao(versao=v1, usuario=usuarios["ger_ti"])
    doc.refresh_from_db()
    assert doc.versao_atual_id == v1.pk and selectors.status_documento(doc) == "publicado"
    with pytest.raises(VersaoJaPublicada):
        services.publicar_versao(versao=v1, usuario=usuarios["ger_ti"])
    services.publicar_versao(versao=v2, usuario=usuarios["ger_ti"])
    doc.refresh_from_db()
    assert doc.versao_atual.numero == 2
    # a v1 continua intacta
    assert VersaoDocumento.objects.get(pk=v1.pk).conteudo == "v1"


def test_rascunho_nao_libera_entrega_so_publicado(usuarios, chamado_dev):
    c = ate_testes(chamado_dev, usuarios["ger_ti"])
    for secao in ("contexto", "regra", "solucao", "teste"):
        doc = Documento.objects.get(chamado=c, secao=secao)
        services.criar_rascunho(documento=doc, conteudo="rascunho", autor=usuarios["colab_ti"])
    with pytest.raises(DocumentacaoIncompleta) as e:
        chamados_services.entregar_chamado(chamado=c, usuario=usuarios["ger_ti"])
    assert len(e.value.extras["faltando"]) == 4
    for secao in ("contexto", "regra", "solucao", "teste"):
        doc = Documento.objects.get(chamado=c, secao=secao)
        services.publicar_versao(versao=doc.versoes.first(), usuario=usuarios["colab_ti"])
    assert chamados_services.entregar_chamado(chamado=c, usuario=usuarios["ger_ti"]).status == "entregue"


def test_destino_exatamente_um():
    with pytest.raises(DestinoInvalido):
        services.criar_secoes(chamado=None, projeto=None)


def test_cobertura_e_pendentes(usuarios, chamado_dev, chamado_sup):
    c_dev = ate_testes(chamado_dev, usuarios["ger_ti"])
    c_sup = ate_testes(chamado_sup, usuarios["ger_ti"])
    pend = selectors.documentacao_pendente()
    assert [c.id for c, _ in pend] == [c_dev.id]
    assert pend[0][1][0] == "Contexto e problema"

    chamados_services.entregar_chamado(chamado=c_sup, usuario=usuarios["ger_ti"])  # sem doc nenhuma
    assert selectors.cobertura() == {
        "chamados_entregues": 1, "secoes_aplicaveis": 4, "secoes_publicadas": 0, "percentual": 0.0,
    }  # fmt: skip
    services.publicar_secao(chamado=c_sup, secao="contexto", conteudo="ctx", autor=usuarios["colab_ti"])
    assert selectors.cobertura()["percentual"] == 25.0
    assert selectors.cobertura(setor=usuarios["colab_prd"].setor)["chamados_entregues"] == 0


def test_api_editor_por_secao(api, usuarios, chamado_dev):
    cli = api(usuarios["colab_ti"])
    chamados_services.atribuir(chamado=chamado_dev, responsavel=usuarios["colab_ti"], usuario=usuarios["ger_ti"])
    r = cli.get(f"/api/v1/documentos/?chamado={chamado_dev.id}")
    assert r.status_code == 200 and len(r.data) == 6
    assert {d["status"] for d in r.data} == {"falta"}
    doc = next(d for d in r.data if d["secao"] == "teste")
    assert doc["obrigatorio"] is True

    r = cli.post(f"/api/v1/documentos/{doc['id']}/versoes/", {"conteudo": "Testado em homologação"})
    assert r.status_code == 201 and r.data["numero"] == 1 and r.data["publicada_em"] is None
    r = cli.get(f"/api/v1/documentos/{doc['id']}/")
    assert r.data["status"] == "rascunho" and r.data["ultima_versao"] == 1 and r.data["versao_atual"] is None

    r = cli.post(f"/api/v1/documentos/{doc['id']}/versoes/1/publicar/")
    assert r.status_code == 200 and r.data["publicada_em"]
    r = cli.get(f"/api/v1/documentos/{doc['id']}/")
    assert r.data["status"] == "publicado" and r.data["resumo"].startswith("Testado")

    r = cli.post(f"/api/v1/documentos/{doc['id']}/versoes/", {"conteudo": "v2 direta", "publicar": True})
    assert r.status_code == 201 and r.data["numero"] == 2 and r.data["publicada_em"]
    assert cli.post(f"/api/v1/documentos/{doc['id']}/versoes/1/publicar/").status_code == 409
    assert cli.post(f"/api/v1/documentos/{doc['id']}/versoes/9/publicar/").status_code == 404


def test_api_escopo_documentos(api, usuarios, chamado_dev, chamado_sup):
    # colab_prd abriu chamado_dev; colab_man abriu chamado_sup
    assert len(api(usuarios["colab_prd"]).get("/api/v1/documentos/").data) == 6
    assert api(usuarios["colab_prd"]).get(f"/api/v1/documentos/?chamado={chamado_sup.id}").data == []
    doc_sup = Documento.objects.filter(chamado=chamado_sup).first()
    assert api(usuarios["colab_prd"]).get(f"/api/v1/documentos/{doc_sup.id}/").status_code == 404
    assert len(api(usuarios["ger_ti"]).get("/api/v1/documentos/").data) == 12
    # Compras: sem acesso ao módulo
    assert api(usuarios["compras"]).get("/api/v1/documentos/").status_code == 403
    # Gerente do setor: vê, não edita
    assert api(usuarios["ger_prd"]).get("/api/v1/documentos/").status_code == 200
    r = api(usuarios["ger_prd"]).post(f"/api/v1/documentos/{doc_sup.id}/versoes/", {"conteudo": "x"})
    assert r.status_code in (403, 404)


def test_api_cobertura_e_pendentes(api, usuarios, chamado_dev):
    ate_testes(chamado_dev, usuarios["ger_ti"])
    r = api(usuarios["ger_ti"]).get("/api/v1/documentos/pendentes/")
    assert r.status_code == 200 and r.data[0]["numero"] == chamado_dev.numero
    assert "Regra de negócio" in r.data[0]["faltando"]
    r = api(usuarios["ger_ti"]).get("/api/v1/documentos/cobertura/")
    assert r.status_code == 200 and r.data["secoes_aplicaveis"] == 0
