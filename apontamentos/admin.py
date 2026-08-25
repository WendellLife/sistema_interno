from django.contrib import admin

from .models import Apontamento, MotivoRetrabalho, TipoTrabalho


@admin.register(TipoTrabalho)
class TipoTrabalhoAdmin(admin.ModelAdmin):
    list_display = ("ordem", "nome", "exige_causa", "contabiliza_capacidade")


@admin.register(MotivoRetrabalho)
class MotivoRetrabalhoAdmin(admin.ModelAdmin):
    list_display = ("nome",)


@admin.register(Apontamento)
class ApontamentoAdmin(admin.ModelAdmin):
    """Leitura. Escrita só pelos serviços (cronômetro, lançamento, aprovação)."""

    list_display = ("usuario", "tipo", "chamado", "projeto", "inicio", "fim", "minutos", "pendente_aprovacao")
    list_filter = ("tipo", "pendente_aprovacao", "lancamento_manual", "usuario__setor")
    readonly_fields = [f.name for f in Apontamento._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
