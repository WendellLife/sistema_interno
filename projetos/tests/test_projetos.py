from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apontamentos import services as ap_services
from apontamentos.models import TipoTrabalho
from core.models import Auditoria
from projetos import selectors, services
from projetos.exceptions import AlocacaoExcedida, EncerramentoSemData, FaseInvalida, ProjetoEncerrado
from projetos.models import Projeto

pytestmark = pytest.mark.django_db


@pytest.fixture
def projeto(usuarios, setores):
    return services.criar_projeto(
        usuario=usuarios["ger_ti"], nome="Dashboard de OEE", setor_solicitante=setores["MAN"],
        patrocinador=usuarios["colab_man"], responsavel=usuarios["colab_ti"], horas_estimadas=40,
        fim_previsto=date.today() + timedelta(days=30),
    )  # fmt: skip


def test_fases_permitidas():
    assert services.fases_permitidas("ideia") == {"analise", "cancelado"}
    assert services.fases_permitidas("testes") == {"ideia", "analise", "aprovado", "fila", "desenvolvimento", "homologacao", "cancelado"}
    assert "concluido" in services.fases_permitidas("implantacao")
    assert services.fases_permitidas("concluido") == set()


def test_mover_no_kanban_e_recusar_pulo(projeto, usuarios):
    p = services.mover_fase(projeto=projeto, para="analise", usuario=usuarios["ger_ti"])
    assert p.fase == "analise"
    with pytest.raises(FaseInvalida):
        services.mover_fase(projeto=p, para="desenvolvimento", usuario=usuarios["ger_ti"])
    p = services.mover_fase(projeto=p, para="ideia", usuario=usuarios["ger_ti"])  # voltar pode
    assert p.fase == "ideia"


def test_concluir_sem_data_e_recusado(projeto, usuarios):
    p = projeto
    for f in ("analise", "aprovado", "fila", "desenvolvimento", "testes", "homologacao", "implantacao"):
        p = services.mover_fase(projeto=p, para=f, usuario=usuarios["ger_ti"])
    with pytest.raises(EncerramentoSemData):
        services.mover_fase(projeto=p, para="concluido", usuario=usuarios["ger_ti"])
    with pytest.raises(EncerramentoSemData):
        services.mover_fase(projeto=p, para="concluido", usuario=usuarios["ger_ti"], encerrado_em=date.today())
    p = services.mover_fase(projeto=p, para="concluido", usuario=usuarios["ger_ti"],
                            encerrado_em=date.today(), situacao_final="Em produção")  # fmt: skip
    assert p.fase == "concluido" and p.encerrado_em == date.today()
    assert Auditoria.objects.filter(acao="projeto.aviso_documentacao", objeto_id=str(p.pk)).exists()
    with pytest.raises(ProjetoEncerrado):
        services.editar_projeto(projeto=p, usuario=usuarios["ger_ti"], nome="x")


def test_banco_recusa_concluido_sem_data(projeto):
    with pytest.raises(IntegrityError), transaction.atomic():
        Projeto.objects.filter(pk=projeto.pk).update(fase="concluido")


def test_cancelar_de_qualquer_fase_com_data(projeto, usuarios):
    p = services.mover_fase(projeto=projeto, para="cancelado", usuario=usuarios["ger_ti"],
                            encerrado_em=date.today(), situacao_final="Cancelado pelo setor")  # fmt: skip
    assert p.fase == "cancelado"


def test_alocacao_limite_100(projeto, usuarios, setores):
    outro = services.criar_projeto(usuario=usuarios["ger_ti"], nome="Outro", setor_solicitante=setores["PRD"],
                                   patrocinador=usuarios["colab_prd"])  # fmt: skip
    services.alocar(projeto=projeto, usuario_alocado=usuarios["colab_ti"], percentual=60, usuario=usuarios["ger_ti"])
    with pytest.raises(AlocacaoExcedida):
        services.alocar(projeto=outro, usuario_alocado=usuarios["colab_ti"], percentual=50, usuario=usuarios["ger_ti"])
    services.alocar(projeto=outro, usuario_alocado=usuarios["colab_ti"], percentual=40, usuario=usuarios["ger_ti"])
    services.alocar(projeto=projeto, usuario_alocado=usuarios["colab_ti"], percentual=30, usuario=usuarios["ger_ti"])  # reduz
    cap = list(selectors.capacidade_alocada_por_pessoa())
    assert cap[0]["id"] == usuarios["colab_ti"].id and cap[0]["alocado"] == 70


def test_horas_realizadas_e_risco(projeto, usuarios):
    tipo = TipoTrabalho.objects.create(nome="Dev", slug="dev")
    ini = timezone.localtime(timezone.now()).replace(hour=8, minute=0, second=0, microsecond=0)
    ap_services.criar_apontamento(usuario=usuarios["colab_ti"], tipo=tipo, projeto=projeto, inicio=ini, fim=ini + timedelta(hours=3))
    p = selectors.base_listagem().get(pk=projeto.pk)
    assert p.minutos_realizados == 180 and p.em_risco is False
    Projeto.objects.filter(pk=p.pk).update(fim_previsto=date.today() - timedelta(days=1))
    assert selectors.base_listagem().get(pk=projeto.pk).em_risco is True
    assert selectors.kpis(selectors.base_listagem()) == {
        "abertos": 1, "em_desenvolvimento": 0, "em_risco": 1, "horas_previstas": 40, "horas_realizadas": 3.0,
    }  # fmt: skip


def test_api_kanban_historico_e_escopo(api, usuarios, setores, projeto):
    ger = api(usuarios["ger_ti"])
    r = ger.get("/api/v1/projetos/")
    assert r.status_code == 200 and r.data["kpis"]["abertos"] == 1
    assert [p["id"] for p in r.data["colunas"]["ideia"]] == [projeto.id]
    assert set(r.data["colunas"]) == {"ideia", "analise", "aprovado", "fila", "desenvolvimento", "testes", "homologacao", "implantacao"}

    r = ger.post(f"/api/v1/projetos/{projeto.id}/fase/", {"fase": "cancelado"})
    assert r.status_code == 400 and r.data["erro"] == "encerramento_sem_data"
    r = ger.post(f"/api/v1/projetos/{projeto.id}/fase/", {"fase": "cancelado", "encerrado_em": "2026-08-24", "situacao_final": "ok"})
    assert r.status_code == 200 and r.data["fase"] == "cancelado"
    assert ger.get("/api/v1/projetos/").data["kpis"]["abertos"] == 0
    assert [p["id"] for p in ger.get("/api/v1/projetos/?historico=true").data] == [projeto.id]

    # Colaborador: sem módulo; Responsável de MAN não existe na fixture — ger_prd vê só PRD (leitura)
    assert api(usuarios["colab_ti"]).get("/api/v1/projetos/").status_code == 403
    assert api(usuarios["ger_prd"]).get("/api/v1/projetos/?historico=true").data == []
    assert api(usuarios["ger_prd"]).post("/api/v1/projetos/", {"nome": "x", "setor_solicitante": setores["PRD"].id,
                                                                "patrocinador": usuarios["ger_prd"].id}).status_code == 403  # fmt: skip
    r = api(usuarios["compras"]).get("/api/v1/projetos/?historico=true")
    assert r.status_code == 200 and len(r.data) == 1


def test_api_marcos_e_alocacoes(api, usuarios, projeto):
    ger = api(usuarios["ger_ti"])
    r = ger.post(f"/api/v1/projetos/{projeto.id}/marcos/", {"nome": "Homologação", "previsto": "2026-09-30"})
    assert r.status_code == 201
    r = ger.post(f"/api/v1/projetos/{projeto.id}/marcos/{r.data['id']}/concluir/", {"concluido_em": "2026-09-28"})
    assert r.status_code == 200 and r.data["concluido_em"] == "2026-09-28"
    r = ger.post(f"/api/v1/projetos/{projeto.id}/alocacoes/", {"usuario": usuarios["colab_ti"].id, "percentual": 120})
    assert r.status_code == 400
    r = ger.post(f"/api/v1/projetos/{projeto.id}/alocacoes/", {"usuario": usuarios["colab_ti"].id, "percentual": 50})
    assert r.status_code == 201
    assert ger.get(f"/api/v1/projetos/{projeto.id}/").data["alocacoes"][0]["percentual"] == 50
