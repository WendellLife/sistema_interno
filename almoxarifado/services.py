"""Almoxarifado: `registrar_movimento` é o ÚNICO ponto que altera `Estoque.saldo`."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core import papeis
from core.auditoria import registrar
from core.numeracao import proximo_numero
from core.permissions import papeis_de

from .exceptions import (
    CotacaoFechada,
    ForaDoEscopo,
    InventarioFechado,
    JustificativaObrigatoria,
    ItemForaDoInventario,
    QuantidadeInvalida,
    SaidaSemReferencia,
    SaldoInsuficiente,
    StatusInvalido,
)
from .models import (
    ENTRADAS,
    ContagemInventario,
    Cotacao,
    Estoque,
    Inventario,
    Item,
    ItemNotaFiscal,
    ItemSolicitacao,
    Movimento,
    NotaFiscal,
    PropostaCotacao,
    Solicitacao,
    Transferencia,
)

T = Movimento.Tipo
D0 = Decimal("0")


def _enfileirar_alerta(item, setor, origem="minimo") -> None:
    from .tasks import alertar_estoque_minimo

    transaction.on_commit(lambda: alertar_estoque_minimo.delay(item.pk, setor.pk, origem))


# ---------------------------------------------------------------- §7 / §8 movimento


@transaction.atomic
def registrar_movimento(
    *, item: Item, setor, tipo: str, quantidade: Decimal, usuario, centro_custo=None,
    sinal: int = 1, justificativa: str = "", chamado=None, projeto=None, os_ref: str = "",
    nota_fiscal=None, solicitacao=None, inventario=None, transferencia=None,
) -> Movimento:  # fmt: skip
    quantidade = Decimal(quantidade)
    if quantidade <= 0:
        raise QuantidadeInvalida()
    if tipo == T.SAIDA and not (centro_custo or chamado or projeto or os_ref):
        raise SaidaSemReferencia()
    if tipo == T.AJUSTE:
        if sinal not in (1, -1):
            raise QuantidadeInvalida()
        if not justificativa:
            raise JustificativaObrigatoria()
    else:
        sinal = 1 if tipo in ENTRADAS else -1

    estoque, _ = Estoque.objects.select_for_update().get_or_create(item=item, setor=setor)
    novo = estoque.saldo + quantidade * sinal
    if novo < 0:
        raise SaldoInsuficiente(item=item, setor=setor, saldo=estoque.saldo, pedido=quantidade)
    anterior = estoque.saldo
    estoque.saldo = novo
    estoque.save(update_fields=["saldo", "atualizado_em"])

    mov = Movimento.objects.create(
        item=item, setor=setor, tipo=tipo, quantidade=quantidade, sinal=sinal, saldo_apos=novo,
        centro_custo=centro_custo, chamado=chamado, projeto=projeto, os_ref=os_ref,
        nota_fiscal=nota_fiscal, solicitacao=solicitacao, inventario=inventario,
        transferencia=transferencia, usuario=usuario, justificativa=justificativa, criado_por=usuario,
    )  # fmt: skip
    registrar(
        usuario=usuario,
        acao=f"estoque.{tipo}",
        objeto=mov,
        antes={"saldo": str(anterior)},
        depois={"saldo": str(novo), "quantidade": str(quantidade), "item": item.codigo, "setor": setor.sigla},
    )
    if novo <= item.estoque_minimo:
        _enfileirar_alerta(item, setor)
    return mov


# ---------------------------------------------------------------- §9 transferência


@transaction.atomic
def transferir(*, item: Item, setor_origem, setor_destino, quantidade, motivo: str, usuario) -> Transferencia:
    """Dois movimentos na mesma transação. Furar o mínimo na origem não bloqueia — marca."""
    if setor_origem.pk == setor_destino.pk:
        raise QuantidadeInvalida()
    quantidade = Decimal(quantidade)
    transf = Transferencia.objects.create(
        item=item, setor_origem=setor_origem, setor_destino=setor_destino,
        quantidade=quantidade, motivo=motivo, criado_por=usuario,
    )  # fmt: skip
    saida = registrar_movimento(
        item=item, setor=setor_origem, tipo=T.TRANSF_SAIDA, quantidade=quantidade,
        usuario=usuario, justificativa=motivo, transferencia=transf,
    )  # fmt: skip
    registrar_movimento(
        item=item, setor=setor_destino, tipo=T.TRANSF_ENTRADA, quantidade=quantidade,
        usuario=usuario, justificativa=motivo, transferencia=transf,
    )  # fmt: skip
    if saida.saldo_apos < item.estoque_minimo:
        transf.fura_minimo_origem = True
        transf.save(update_fields=["fura_minimo_origem"])
        _enfileirar_alerta(item, setor_origem, origem="transferencia")
    return transf


# ---------------------------------------------------------------- solicitações


@transaction.atomic
def criar_solicitacao(
    *, solicitante, centro_custo, itens: list[dict], os_ref: str = "", urgente: bool = False,
    setor=None, origem: str = Solicitacao.Origem.SISTEMA,
) -> Solicitacao:  # fmt: skip
    if not itens:
        raise QuantidadeInvalida()
    sol = Solicitacao.objects.create(
        numero=proximo_numero("SOL"), setor=setor or solicitante.setor, solicitante=solicitante,
        centro_custo=centro_custo, os_ref=os_ref, urgente=urgente, origem=origem, criado_por=solicitante,
    )  # fmt: skip
    for linha in itens:
        if Decimal(linha["quantidade"]) <= 0:
            raise QuantidadeInvalida()
        ItemSolicitacao.objects.create(solicitacao=sol, item=linha["item"], quantidade=linha["quantidade"])
    registrar(usuario=solicitante, acao="solicitacao.criar", objeto=sol, antes=None,
              depois={"status": sol.status, "itens": len(itens)})  # fmt: skip
    return sol


PAPEIS_APROVAM_SOLICITACAO = {papeis.GERENTE_SETOR, papeis.ADMINISTRADOR}


def _pode_aprovar_solicitacao(user, sol: Solicitacao) -> bool:
    meus = papeis_de(user)
    if papeis.ADMINISTRADOR in meus:
        return True
    return papeis.GERENTE_SETOR in meus and sol.setor_id == user.setor_id


@transaction.atomic
def aprovar_solicitacao(*, solicitacao: Solicitacao, aprovador) -> Solicitacao:
    sol = Solicitacao.objects.select_for_update().get(pk=solicitacao.pk)
    if sol.status != Solicitacao.Status.ABERTA:
        raise StatusInvalido(sol.status, "aprovar")
    if not _pode_aprovar_solicitacao(aprovador, sol):
        raise ForaDoEscopo("Só o gerente do setor aprova solicitações do setor.")
    sol.status = Solicitacao.Status.APROVADA
    sol.aprovada_por = aprovador
    sol.aprovada_em = timezone.now()
    sol.save(update_fields=["status", "aprovada_por", "aprovada_em", "atualizado_em"])
    registrar(usuario=aprovador, acao="solicitacao.aprovar", objeto=sol,
              antes={"status": "aberta"}, depois={"status": "aprovada"})  # fmt: skip
    return sol


@transaction.atomic
def negar_solicitacao(*, solicitacao: Solicitacao, aprovador, motivo: str) -> Solicitacao:
    sol = Solicitacao.objects.select_for_update().get(pk=solicitacao.pk)
    if sol.status != Solicitacao.Status.ABERTA:
        raise StatusInvalido(sol.status, "negar")
    if not _pode_aprovar_solicitacao(aprovador, sol):
        raise ForaDoEscopo("Só o gerente do setor nega solicitações do setor.")
    sol.status = Solicitacao.Status.NEGADA
    sol.motivo_negacao = motivo
    sol.save(update_fields=["status", "motivo_negacao", "atualizado_em"])
    registrar(usuario=aprovador, acao="solicitacao.negar", objeto=sol,
              antes={"status": "aberta"}, depois={"status": "negada", "motivo": motivo})  # fmt: skip
    return sol


@transaction.atomic
def atender_solicitacao(
    *, solicitacao: Solicitacao, usuario, quantidades: dict[int, Decimal] | None = None
) -> Solicitacao:
    """Gera saídas com o centro de custo da solicitação. `quantidades` = {item_id: qtd};
    ausente = tudo o que falta. Parcial permitido: fica `aprovada` até completar."""
    sol = Solicitacao.objects.select_for_update().get(pk=solicitacao.pk)
    if sol.status != Solicitacao.Status.APROVADA:
        raise StatusInvalido(sol.status, "atender")
    linhas = list(sol.itens.select_related("item").select_for_update())
    atendeu_algo = False
    for linha in linhas:
        if quantidades is not None and linha.item_id not in quantidades:
            continue  # atendimento parcial: item fora do mapa NÃO sai do estoque
        qtd = Decimal(quantidades[linha.item_id]) if quantidades is not None else linha.pendente
        if qtd <= 0:
            continue
        if qtd > linha.pendente:
            raise QuantidadeInvalida()
        registrar_movimento(
            item=linha.item, setor=sol.setor, tipo=T.SAIDA, quantidade=qtd, usuario=usuario,
            centro_custo=sol.centro_custo, os_ref=sol.os_ref, solicitacao=sol,
        )  # fmt: skip
        linha.quantidade_atendida += qtd
        linha.save(update_fields=["quantidade_atendida"])
        atendeu_algo = True
    if not atendeu_algo:
        raise QuantidadeInvalida()
    completa = all(li.pendente <= 0 for li in linhas)
    if completa:
        sol.status = Solicitacao.Status.ATENDIDA
        sol.save(update_fields=["status", "atualizado_em"])
    registrar(usuario=usuario, acao="solicitacao.atender", objeto=sol,
              antes={"status": "aprovada"}, depois={"status": sol.status, "completa": completa})  # fmt: skip
    return sol


# ---------------------------------------------------------------- nota fiscal


@transaction.atomic
def entrada_por_nota(*, usuario, setor, itens: list[dict], **dados_nota) -> NotaFiscal:
    """Cria a NF e gera uma ENTRADA por item com a `quantidade_recebida`; atualiza custo unitário."""
    if not itens:
        raise QuantidadeInvalida()
    nota = NotaFiscal.objects.create(setor=setor, conferida_por=usuario, criado_por=usuario, **dados_nota)
    for linha in itens:
        item = linha["item"]
        recebida = Decimal(linha["quantidade_recebida"])
        pedida = Decimal(linha.get("quantidade_pedida", recebida))
        divergencia = linha.get("divergencia", "")
        if recebida != pedida and not divergencia:
            divergencia = f"Pedido {pedida}, recebido {recebida}"
        ItemNotaFiscal.objects.create(
            nota=nota, item=item, quantidade_pedida=pedida, quantidade_recebida=recebida,
            custo_unitario=linha["custo_unitario"], divergencia=divergencia,
        )  # fmt: skip
        if recebida > 0:
            registrar_movimento(
                item=item, setor=setor, tipo=T.ENTRADA, quantidade=recebida, usuario=usuario,
                nota_fiscal=nota, justificativa=f"NF {nota.numero}",
            )  # fmt: skip
        if linha["custo_unitario"] and item.custo_unitario != linha["custo_unitario"]:
            Item.objects.filter(pk=item.pk).update(custo_unitario=linha["custo_unitario"])
    registrar(usuario=usuario, acao="nota_fiscal.entrada", objeto=nota, antes=None,
              depois={"itens": len(itens), "valor_total": str(nota.valor_total)})  # fmt: skip
    return nota


# ---------------------------------------------------------------- §10 inventário


@transaction.atomic
def abrir_inventario(*, setor, responsavel, itens=None) -> Inventario:
    """Abre com snapshot dos saldos do setor (todos os itens com estoque, ou os informados)."""
    inv = Inventario.objects.create(setor=setor, responsavel=responsavel, criado_por=responsavel)
    estoques = Estoque.objects.filter(setor=setor).select_related("item")
    if itens:
        estoques = estoques.filter(item__in=itens)
    ContagemInventario.objects.bulk_create(
        ContagemInventario(inventario=inv, item=e.item, saldo_sistema=e.saldo) for e in estoques
    )
    registrar(usuario=responsavel, acao="inventario.abrir", objeto=inv, antes=None,
              depois={"setor": setor.sigla, "itens": estoques.count()})  # fmt: skip
    return inv


@transaction.atomic
def registrar_contagens(*, inventario: Inventario, contagens: dict[int, Decimal], usuario) -> int:
    inv = Inventario.objects.select_for_update().get(pk=inventario.pk)
    if inv.status == Inventario.Status.FECHADO:
        raise InventarioFechado()
    n = 0
    por_item = {c.item_id: c for c in inv.contagens.select_related("item")}
    for item_id, contado in contagens.items():
        c = por_item.get(int(item_id))
        if c is None:
            raise ItemForaDoInventario(Item.objects.filter(pk=item_id).values_list("codigo", flat=True).first() or str(item_id))
        c.saldo_contado = Decimal(contado)
        c.save(update_fields=["saldo_contado"])
        n += 1
    return n


@transaction.atomic
def fechar_inventario(*, inventario: Inventario, usuario) -> Inventario:
    """Cada contagem divergente vira AJUSTE. Sem contagem = ignorado, não zerado."""
    inv = Inventario.objects.select_for_update().get(pk=inventario.pk)
    if inv.status == Inventario.Status.FECHADO:
        raise InventarioFechado()
    divergencias = 0
    impacto = D0
    for c in inv.contagens.select_related("item").filter(saldo_contado__isnull=False):
        # Compara com o saldo ATUAL (pode ter havido movimento após o snapshot)
        atual = Estoque.objects.filter(item=c.item, setor=inv.setor).values_list("saldo", flat=True).first() or D0
        diff = c.saldo_contado - atual
        if diff == 0:
            continue
        registrar_movimento(
            item=c.item, setor=inv.setor, tipo=T.AJUSTE, quantidade=abs(diff),
            sinal=1 if diff > 0 else -1, usuario=usuario, inventario=inv,
            justificativa=f"Inventário #{inv.pk}",
        )  # fmt: skip
        divergencias += 1
        impacto += abs(diff) * c.item.custo_unitario
    inv.status = Inventario.Status.FECHADO
    inv.fechado_em = timezone.now()
    inv.divergencias = divergencias
    inv.impacto_valor = impacto.quantize(Decimal("0.01"))
    inv.save(update_fields=["status", "fechado_em", "divergencias", "impacto_valor", "atualizado_em"])
    registrar(usuario=usuario, acao="inventario.fechar", objeto=inv, antes={"status": "aberto"},
              depois={"status": "fechado", "divergencias": divergencias, "impacto_valor": str(inv.impacto_valor)})  # fmt: skip
    return inv


# ---------------------------------------------------------------- cotações


@transaction.atomic
def abrir_cotacao(*, item: Item, quantidade, prazo_resposta, usuario) -> Cotacao:
    if Decimal(quantidade) <= 0:
        raise QuantidadeInvalida()
    cot = Cotacao.objects.create(item=item, quantidade=quantidade, prazo_resposta=prazo_resposta, criado_por=usuario)
    registrar(usuario=usuario, acao="cotacao.abrir", objeto=cot, antes=None, depois={"item": item.codigo})
    return cot


@transaction.atomic
def registrar_proposta(*, cotacao: Cotacao, fornecedor: str, valor_unitario, prazo_entrega_dias: int, usuario) -> PropostaCotacao:
    cot = Cotacao.objects.select_for_update().get(pk=cotacao.pk)
    if cot.status == Cotacao.Status.FECHADA:
        raise CotacaoFechada()
    prop = PropostaCotacao.objects.create(
        cotacao=cot, fornecedor=fornecedor, valor_unitario=valor_unitario, prazo_entrega_dias=prazo_entrega_dias
    )
    if cot.status == Cotacao.Status.ABERTA:
        cot.status = Cotacao.Status.RESPONDIDA
        cot.save(update_fields=["status", "atualizado_em"])
    return prop


@transaction.atomic
def escolher_proposta(*, proposta: PropostaCotacao, usuario) -> PropostaCotacao:
    cot = Cotacao.objects.select_for_update().get(pk=proposta.cotacao_id)
    if cot.status == Cotacao.Status.FECHADA:
        raise CotacaoFechada()
    cot.propostas.update(escolhida=False)
    PropostaCotacao.objects.filter(pk=proposta.pk).update(escolhida=True)
    cot.status = Cotacao.Status.FECHADA
    cot.save(update_fields=["status", "atualizado_em"])
    registrar(usuario=usuario, acao="cotacao.escolher", objeto=cot, antes={"status": "respondida"},
              depois={"status": "fechada", "proposta": proposta.pk, "fornecedor": proposta.fornecedor})  # fmt: skip
    return PropostaCotacao.objects.get(pk=proposta.pk)
