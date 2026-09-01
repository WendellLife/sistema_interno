from django.contrib import admin

from .models import (
    AlertaReposicao,
    Cotacao,
    Estoque,
    Inventario,
    Item,
    Movimento,
    NotaFiscal,
    Solicitacao,
    Transferencia,
)  # fmt: skip


class SomenteLeitura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("codigo", "descricao", "unidade", "setor_dono", "estoque_minimo", "custo_unitario", "ativo")
    list_filter = ("setor_dono", "ativo")
    search_fields = ("codigo", "descricao", "codigo_sankhya")


@admin.register(Estoque)
class EstoqueAdmin(SomenteLeitura):
    """Saldo só muda por `registrar_movimento`."""

    list_display = ("item", "setor", "saldo", "atualizado_em")
    list_filter = ("setor",)


@admin.register(Movimento)
class MovimentoAdmin(SomenteLeitura):
    """Imutável — correção é AJUSTE novo."""

    list_display = ("criado_em", "item", "setor", "tipo", "quantidade", "sinal", "saldo_apos", "usuario")
    list_filter = ("tipo", "setor")
    search_fields = ("item__codigo", "justificativa", "os_ref")

    def has_add_permission(self, request):
        return False


@admin.register(Solicitacao)
class SolicitacaoAdmin(SomenteLeitura):
    list_display = ("numero", "setor", "solicitante", "status", "urgente", "criado_em")
    list_filter = ("status", "setor")


@admin.register(NotaFiscal)
class NotaFiscalAdmin(SomenteLeitura):
    list_display = ("numero", "serie", "fornecedor", "emissao", "valor_total", "setor")


@admin.register(Transferencia)
class TransferenciaAdmin(SomenteLeitura):
    list_display = ("criado_em", "item", "setor_origem", "setor_destino", "quantidade", "fura_minimo_origem")


@admin.register(Inventario)
class InventarioAdmin(SomenteLeitura):
    list_display = ("id", "setor", "responsavel", "status", "divergencias", "impacto_valor", "fechado_em")


@admin.register(Cotacao)
class CotacaoAdmin(SomenteLeitura):
    list_display = ("id", "item", "quantidade", "prazo_resposta", "status")


@admin.register(AlertaReposicao)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "item", "setor", "saldo", "minimo", "origem", "resolvido_em")
    list_filter = ("origem", "setor")
