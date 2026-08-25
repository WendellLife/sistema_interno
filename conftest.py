"""Fixtures globais: setores, papéis e um usuário por papel."""

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from chamados.models import Categoria, RegraSLA
from core import papeis
from core.models import Setor, User
from core.permissions import invalidar_papeis


@pytest.fixture
def setores(db):
    nomes = [("TI", "TI"), ("Produção", "PRD"), ("Manutenção", "MAN"), ("Compras", "CMP")]
    return {sigla: Setor.objects.create(nome=nome, sigla=sigla) for nome, sigla in nomes}


@pytest.fixture
def grupos(db):
    return {n: Group.objects.get_or_create(name=n)[0] for n in papeis.TODOS}


def criar_usuario(username, setor, papel, grupos, matricula=None):
    u = User.objects.create_user(
        username=username,
        password="x",
        email=f"{username}@t.local",
        first_name=username.title(),
        matricula=matricula or username[:20],
        setor=setor,
    )
    u.groups.set([grupos[papel]])
    invalidar_papeis(u)
    return u


@pytest.fixture
def usuarios(setores, grupos):
    return {
        "colab_prd": criar_usuario("colab_prd", setores["PRD"], papeis.COLABORADOR, grupos),
        "colab_prd2": criar_usuario("colab_prd2", setores["PRD"], papeis.COLABORADOR, grupos),
        "colab_man": criar_usuario("colab_man", setores["MAN"], papeis.COLABORADOR, grupos),
        "resp_prd": criar_usuario("resp_prd", setores["PRD"], papeis.RESPONSAVEL, grupos),
        "ger_prd": criar_usuario("ger_prd", setores["PRD"], papeis.GERENTE_SETOR, grupos),
        "ger_ti": criar_usuario("ger_ti", setores["TI"], papeis.GERENTE_TI, grupos),
        "colab_ti": criar_usuario("colab_ti", setores["TI"], papeis.COLABORADOR, grupos),
        "compras": criar_usuario("compras", setores["CMP"], papeis.COMPRAS, grupos),
        "admin": criar_usuario("admin", setores["TI"], papeis.ADMINISTRADOR, grupos),
    }


@pytest.fixture
def categorias(db):
    dev = Categoria.objects.create(nome="Desenvolvimento", slug="desenvolvimento", exige_documentacao=True)
    sup = Categoria.objects.create(nome="Suporte", slug="suporte", exige_documentacao=False)
    for c in (dev, sup):
        for prio, h in {"critica": 4, "alta": 24, "media": 48, "baixa": 72}.items():
            RegraSLA.objects.create(categoria=c, prioridade=prio, horas_uteis=h)
    return {"dev": dev, "suporte": sup}


@pytest.fixture
def api():
    def _como(user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    return _como
