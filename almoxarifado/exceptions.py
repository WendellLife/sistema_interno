from rest_framework import status

from core.exceptions import RegraDeNegocio


class SaldoInsuficiente(RegraDeNegocio):
    codigo = "saldo_insuficiente"

    def __init__(self, *, item, setor, saldo, pedido):
        super().__init__(
            f"Saldo insuficiente em {setor.nome}.",
            item=item.codigo, saldo=str(saldo), pedido=str(pedido),
        )  # fmt: skip


class QuantidadeInvalida(RegraDeNegocio):
    codigo = "quantidade_invalida"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self):
        super().__init__("A quantidade deve ser maior que zero.")


class SaidaSemReferencia(RegraDeNegocio):
    """Regra §8: saída exige centro de custo, chamado, projeto ou OS."""

    codigo = "saida_sem_referencia"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self):
        super().__init__("Saída exige centro de custo, chamado, projeto ou OS de referência.")


class StatusInvalido(RegraDeNegocio):
    codigo = "status_invalido"

    def __init__(self, de: str, acao: str):
        super().__init__(f"Não é possível '{acao}' uma solicitação '{de}'.", de=de, acao=acao)


class InventarioFechado(RegraDeNegocio):
    codigo = "inventario_fechado"

    def __init__(self):
        super().__init__("Este inventário já foi fechado.")


class ItemForaDoInventario(RegraDeNegocio):
    codigo = "item_fora_do_inventario"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self, codigo: str):
        super().__init__(f"O item {codigo} não faz parte deste inventário.", item=codigo)


class CotacaoFechada(RegraDeNegocio):
    codigo = "cotacao_fechada"

    def __init__(self):
        super().__init__("Esta cotação já está fechada.")


class ForaDoEscopo(RegraDeNegocio):
    codigo = "fora_do_escopo"
    status_http = status.HTTP_403_FORBIDDEN


class JustificativaObrigatoria(RegraDeNegocio):
    codigo = "justificativa_obrigatoria"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self):
        super().__init__("Ajuste de estoque exige justificativa.")
