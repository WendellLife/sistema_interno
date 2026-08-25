from django.contrib import admin

from .models import Anexo, Categoria, Chamado, Comentario, HistoricoChamado, RegraSLA


class ComentarioInline(admin.TabularInline):
    model = Comentario
    extra = 0


class HistoricoInline(admin.TabularInline):
    model = HistoricoChamado
    extra = 0
    can_delete = False
    readonly_fields = ("quando", "usuario", "texto")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    """Status NÃO é editável pelo admin — transições só via serviço (respeita documentação)."""

    list_display = ("numero", "titulo", "setor_origem", "categoria", "prioridade", "status", "responsavel", "sla_previsto")
    list_filter = ("status", "prioridade", "categoria", "setor_origem")
    search_fields = ("numero", "titulo")
    readonly_fields = ("numero", "status", "sla_previsto", "sla_cumprido", "entregue_em")
    inlines = [ComentarioInline, HistoricoInline]


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "exige_documentacao")


@admin.register(RegraSLA)
class RegraSLAAdmin(admin.ModelAdmin):
    list_display = ("categoria", "prioridade", "horas_uteis")


@admin.register(Anexo)
class AnexoAdmin(admin.ModelAdmin):
    list_display = ("chamado", "nome_original", "tamanho_bytes", "criado_em")
