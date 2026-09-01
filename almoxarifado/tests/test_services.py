import threading
from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from almoxarifado import selectors, services
from almoxarifado.exceptions import (
    CotacaoFechada,
    ForaDoEscopo,
    InventarioFechado,
    JustificativaObrigatoria,
    QuantidadeInvalida,
    SaidaSemReferencia,
    SaldoInsuficiente,
    StatusInvalido,
)
from almoxarifado.models import AlertaReposicao, Estoque, Movimento
from core.models import Auditoria

pytestmark = pytest.mark.django_db
D = Decimal


# ---------------------------------------------------------------- §7 saldo nunca negativo


def test_saida_maior_que_saldo_recusada(itens, setores, usuarios, cc, estoque_inicial):
    with pytest.raises(SaldoInsuficiente) as e:
        services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="saida", quantidade=11,
                                     usuario=usuarios["colab_man"], centro_custo=cc["MAN"])  # fmt: skip
    assert e.value.como_dict() == {
        "erro": "saldo_insuficiente", "item": "MRO-4471", "saldo": "10.000", "pedido": "11",
        "mensagem": "Saldo insuficiente em Manutenção.",
    }  # fmt: skip
    assert selectors.saldo(itens["parafuso"], setores["MAN"]) == 10


def test_banco_recusa_saldo_negativo(itens, setores):
    with pytest.raises(IntegrityError), transaction.atomic():
        Estoque.objects.create(item=itens["parafuso"], setor=setores["MAN"], saldo=-1)


def test_quantidade_zero_ou_negativa(itens, setores, usuarios):
    for q in (0, -3):
        with pytest.raises(QuantidadeInvalida):
            services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="entrada",
                                         quantidade=q, usuario=usuarios["admin"])  # fmt: skip


@pytest.mark.django_db(transaction=True)
def test_duas_saidas_concorrentes_de_6_com_saldo_10(itens, setores, usuarios, cc, estoque_inicial):
    resultados = []
    barreira = threading.Barrier(2)

    def worker():
        try:
            barreira.wait()
            services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="saida",
                                         quantidade=6, usuario=usuarios["colab_man"], centro_custo=cc["MAN"])  # fmt: skip
            resultados.append("ok")
        except SaldoInsuficiente:
            resultados.append("insuficiente")
        finally:
            connection.close()

    ts = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(resultados) == ["insuficiente", "ok"]
    assert selectors.saldo(itens["parafuso"], setores["MAN"]) == 4
    assert selectors.reconciliar() == []


def test_movimento_grava_saldo_apos_e_auditoria(itens, setores, usuarios, cc, estoque_inicial):
    m = services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="saida", quantidade=3,
                                     usuario=usuarios["colab_man"], centro_custo=cc["MAN"])  # fmt: skip
    assert m.saldo_apos == 7 and m.sinal == -1
    a = Auditoria.objects.get(acao="estoque.saida", objeto_id=str(m.pk))
    assert a.antes == {"saldo": "10.000"} and a.depois["saldo"] == "7.000"


def test_reconciliacao_apos_varios_movimentos(itens, setores, usuarios, cc, estoque_inicial):
    u = usuarios["admin"]
    services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="saida", quantidade=2, usuario=u, os_ref="OS-1")
    services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="ajuste", quantidade=1, sinal=-1, usuario=u, justificativa="quebra")
    services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="entrada", quantidade=5, usuario=u)
    assert selectors.saldo(itens["parafuso"], setores["MAN"]) == 12
    assert selectors.reconciliar() == []
    Estoque.objects.filter(item=itens["parafuso"], setor=setores["MAN"]).update(saldo=99)
    assert len(selectors.reconciliar()) == 1


def test_ajuste_exige_justificativa(itens, setores, usuarios, estoque_inicial):
    with pytest.raises(JustificativaObrigatoria):
        services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="ajuste", quantidade=1,
                                     sinal=-1, usuario=usuarios["admin"])  # fmt: skip


# ---------------------------------------------------------------- §8 saída exige referência


def test_saida_sem_referencia_400_e_consumo_geral(itens, setores, usuarios, cc, estoque_inicial):
    u = usuarios["colab_man"]
    with pytest.raises(SaidaSemReferencia):
        services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="saida", quantidade=1, usuario=u)
    geral = services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="saida", quantidade=1,
                                         usuario=u, centro_custo=cc["MAN"])  # fmt: skip
    com_os = services.registrar_movimento(item=itens["parafuso"], setor=setores["MAN"], tipo="saida", quantidade=1,
                                          usuario=u, os_ref="OS-77")  # fmt: skip
    assert geral.consumo_geral is True and com_os.consumo_geral is False
    assert [m.pk for m in selectors.consumo(sem_os=True)] == [geral.pk]
    assert [m.pk for m in selectors.consumo(sem_os=False)] == [com_os.pk]


# ---------------------------------------------------------------- §9 transferência


def test_transferencia_fura_minimo_marca_e_alerta(itens, setores, usuarios, estoque_inicial, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        t = services.transferir(item=itens["parafuso"], setor_origem=setores["MAN"], setor_destino=setores["PRD"],
                                quantidade=8, motivo="Linha 2 parada", usuario=usuarios["ger_ti"])  # fmt: skip
    assert t.fura_minimo_origem is True
    assert selectors.saldo(itens["parafuso"], setores["MAN"]) == 2
    assert selectors.saldo(itens["parafuso"], setores["PRD"]) == 8
    movs = Movimento.objects.filter(transferencia=t).order_by("id")
    assert [m.tipo for m in movs] == ["transf_saida", "transf_entrada"]
    assert AlertaReposicao.objects.filter(item=itens["parafuso"], setor=setores["MAN"], resolvido_em__isnull=True).count() == 1
    assert selectors.reconciliar() == []


def test_transferencia_atomica_quando_falta_saldo(itens, setores, usuarios, estoque_inicial):
    with pytest.raises(SaldoInsuficiente):
        services.transferir(item=itens["parafuso"], setor_origem=setores["MAN"], setor_destino=setores["PRD"],
                            quantidade=50, motivo="x", usuario=usuarios["ger_ti"])  # fmt: skip
    assert Movimento.objects.filter(tipo__startswith="transf").count() == 0
    assert selectors.saldo(itens["parafuso"], setores["MAN"]) == 10


def test_transferencia_mesmo_setor_recusada(itens, setores, usuarios, estoque_inicial):
    with pytest.raises(QuantidadeInvalida):
        services.transferir(item=itens["parafuso"], setor_origem=setores["MAN"], setor_destino=setores["MAN"],
                            quantidade=1, motivo="x", usuario=usuarios["ger_ti"])  # fmt: skip


# ---------------------------------------------------------------- solicitações


def test_fluxo_solicitacao_parcial(itens, setores, usuarios, cc, estoque_inicial):
    sol = services.criar_solicitacao(
        solicitante=usuarios["colab_man"], centro_custo=cc["MAN"], os_ref="OS-9",
        itens=[{"item": itens["parafuso"], "quantidade": 6}, {"item": itens["oleo"], "quantidade": 2}],
    )  # fmt: skip
    assert sol.numero.startswith("SOL-") and sol.status == "aberta"
    with pytest.raises(StatusInvalido):
        services.atender_solicitacao(solicitacao=sol, usuario=usuarios["resp_prd"])
    with pytest.raises(ForaDoEscopo):  # gerente de PRD não aprova solicitação de MAN
        services.aprovar_solicitacao(solicitacao=sol, aprovador=usuarios["ger_prd"])
    sol = services.aprovar_solicitacao(solicitacao=sol, aprovador=usuarios["admin"])
    assert sol.status == "aprovada"

    sol = services.atender_solicitacao(solicitacao=sol, usuario=usuarios["admin"],
                                       quantidades={itens["parafuso"].id: D("4")})  # fmt: skip
    assert sol.status == "aprovada"  # parcial
    linha = sol.itens.get(item=itens["parafuso"])
    assert linha.quantidade_atendida == 4 and linha.pendente == 2
    saida = Movimento.objects.get(solicitacao=sol)
    assert saida.centro_custo == cc["MAN"] and saida.os_ref == "OS-9" and saida.consumo_geral is False

    sol = services.atender_solicitacao(solicitacao=sol, usuario=usuarios["admin"])  # o resto
    assert sol.status == "atendida"
    assert selectors.saldo(itens["parafuso"], setores["MAN"]) == 4
    assert selectors.saldo(itens["oleo"], setores["MAN"]) == 2
    # Já atendida: a recusa é de ESTADO, não de quantidade.
    with pytest.raises(StatusInvalido):
        services.atender_solicitacao(solicitacao=sol, usuario=usuarios["admin"])


def test_atender_alem_do_pedido_recusado(itens, setores, usuarios, cc, estoque_inicial):
    sol = services.criar_solicitacao(solicitante=usuarios["colab_man"], centro_custo=cc["MAN"],
                                     itens=[{"item": itens["parafuso"], "quantidade": 2}])  # fmt: skip
    services.aprovar_solicitacao(solicitacao=sol, aprovador=usuarios["admin"])
    with pytest.raises(QuantidadeInvalida):
        services.atender_solicitacao(solicitacao=sol, usuario=usuarios["admin"], quantidades={itens["parafuso"].id: D("3")})


# ---------------------------------------------------------------- nota fiscal


def test_entrada_por_nota_gera_entradas_e_atualiza_custo(itens, setores, usuarios):
    nota = services.entrada_por_nota(
        usuario=usuarios["compras"], setor=setores["MAN"], numero="12345", serie="1", fornecedor="Parafusos SA",
        cnpj="00.000.000/0001-00", emissao=date(2026, 8, 20), valor_total=D("215.00"),
        itens=[
            {"item": itens["parafuso"], "quantidade_pedida": 100, "quantidade_recebida": 100, "custo_unitario": D("1.65")},
            {"item": itens["oleo"], "quantidade_pedida": 2, "quantidade_recebida": 1, "custo_unitario": D("50.00")},
        ],
    )  # fmt: skip
    assert nota.itens.count() == 2
    assert selectors.saldo(itens["parafuso"], setores["MAN"]) == 100
    assert selectors.saldo(itens["oleo"], setores["MAN"]) == 1
    assert nota.itens.get(item=itens["oleo"]).divergencia == "Pedido 2, recebido 1"
    itens["parafuso"].refresh_from_db()
    assert itens["parafuso"].custo_unitario == D("1.65")
    assert Movimento.objects.filter(nota_fiscal=nota, tipo="entrada").count() == 2


# ---------------------------------------------------------------- §10 inventário


def test_inventario_5_itens_2_divergentes(itens, setores, usuarios, estoque_inicial):
    u = usuarios["compras"]
    man = setores["MAN"]
    # mais 3 itens no MAN para totalizar 5
    from almoxarifado.models import Item

    extras = [
        Item.objects.create(codigo=f"X-{i}", descricao=f"Extra {i}", unidade="UN", setor_dono=man, custo_unitario=D("10.00"))
        for i in range(3)
    ]
    for it in extras:
        services.registrar_movimento(item=it, setor=man, tipo="entrada", quantidade=10, usuario=u)

    inv = services.abrir_inventario(setor=man, responsavel=u)
    assert inv.contagens.count() == 5
    assert inv.contagens.get(item=itens["parafuso"]).saldo_sistema == 10

    services.registrar_contagens(inventario=inv, usuario=u, contagens={
        itens["parafuso"].id: D("8"),   # -2 × 1.50 = 3.00
        itens["oleo"].id: D("4"),       # igual
        extras[0].id: D("13"),          # +3 × 10.00 = 30.00
        extras[1].id: D("10"),          # igual
        # extras[2] sem contagem → ignorado, não zerado
    })  # fmt: skip
    inv = services.fechar_inventario(inventario=inv, usuario=u)
    assert inv.status == "fechado" and inv.divergencias == 2
    assert inv.impacto_valor == D("33.00")
    ajustes = Movimento.objects.filter(inventario=inv, tipo="ajuste")
    assert ajustes.count() == 2 and all(m.justificativa == f"Inventário #{inv.pk}" for m in ajustes)
    assert selectors.saldo(itens["parafuso"], man) == 8
    assert selectors.saldo(extras[0], man) == 13
    assert selectors.saldo(extras[2], man) == 10
    assert selectors.reconciliar() == []
    with pytest.raises(InventarioFechado):
        services.registrar_contagens(inventario=inv, usuario=u, contagens={itens["oleo"].id: D("1")})


def test_um_inventario_aberto_por_setor(setores, usuarios):
    services.abrir_inventario(setor=setores["MAN"], responsavel=usuarios["compras"])
    with pytest.raises(IntegrityError), transaction.atomic():
        services.abrir_inventario(setor=setores["MAN"], responsavel=usuarios["compras"])


# ---------------------------------------------------------------- cotação


def test_cotacao_escolha_unica(itens, usuarios):
    u = usuarios["compras"]
    cot = services.abrir_cotacao(item=itens["luva"], quantidade=200, prazo_resposta=date(2026, 9, 1), usuario=u)
    p1 = services.registrar_proposta(cotacao=cot, fornecedor="A", valor_unitario=D("3.90"), prazo_entrega_dias=5, usuario=u)
    p2 = services.registrar_proposta(cotacao=cot, fornecedor="B", valor_unitario=D("3.50"), prazo_entrega_dias=12, usuario=u)
    cot.refresh_from_db()
    assert cot.status == "respondida"
    services.escolher_proposta(proposta=p2, usuario=u)
    cot.refresh_from_db()
    assert cot.status == "fechada" and cot.propostas.filter(escolhida=True).count() == 1
    with pytest.raises(CotacaoFechada):
        services.escolher_proposta(proposta=p1, usuario=u)
