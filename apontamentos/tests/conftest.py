import pytest

from apontamentos.models import MOTIVOS_INICIAIS, TIPOS_INICIAIS, MotivoRetrabalho, TipoTrabalho
from chamados import services as chamados_services


@pytest.fixture
def tipos(db):
    out = {}
    for ordem, (nome, slug, exige, contabiliza) in enumerate(TIPOS_INICIAIS):
        out[slug] = TipoTrabalho.objects.create(
            nome=nome, slug=slug, exige_causa=exige, contabiliza_capacidade=contabiliza, ordem=ordem
        )
    return out


@pytest.fixture
def motivos(db):
    return [MotivoRetrabalho.objects.create(nome=n) for n in MOTIVOS_INICIAIS]


@pytest.fixture
def chamado(usuarios, categorias):
    return chamados_services.abrir_chamado(
        solicitante=usuarios["colab_prd"], titulo="T", descricao="d",
        categoria=categorias["suporte"], prioridade="media",
    )  # fmt: skip
