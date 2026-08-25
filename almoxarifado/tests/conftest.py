from decimal import Decimal

import pytest

from almoxarifado import services
from almoxarifado.models import Item
from core.models import CentroCusto


@pytest.fixture
def itens(setores):
    return {
        "parafuso": Item.objects.create(codigo="MRO-4471", descricao="Parafuso sextavado M8", unidade="UN",
                                        setor_dono=setores["MAN"], estoque_minimo=5, custo_unitario=Decimal("1.50")),
        "luva": Item.objects.create(codigo="EPI-0012", descricao="Luva nitrílica G", unidade="PC",
                                    setor_dono=setores["PRD"], estoque_minimo=20, custo_unitario=Decimal("4.00")),
        "oleo": Item.objects.create(codigo="MRO-0900", descricao="Óleo lubrificante 1L", unidade="L",
                                    setor_dono=setores["MAN"], estoque_minimo=2, custo_unitario=Decimal("30.00")),
    }  # fmt: skip


@pytest.fixture
def cc(setores):
    return {
        "MAN": CentroCusto.objects.create(codigo="2001", descricao="Operação Manutenção", setor=setores["MAN"]),
        "PRD": CentroCusto.objects.create(codigo="2002", descricao="Operação Produção", setor=setores["PRD"]),
    }


@pytest.fixture
def estoque_inicial(itens, setores, usuarios):
    """MAN: parafuso 10, óleo 4. PRD: luva 50."""
    u = usuarios["admin"]
    services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="entrada", quantidade=10, usuario=u)
    services.registrar_movimento(item=itens["oleo"], setor=setores["MAN"], tipo="entrada", quantidade=4, usuario=u)
    services.registrar_movimento(item=itens["luva"], setor=setores["PRD"], tipo="entrada", quantidade=50, usuario=u)
    return True
