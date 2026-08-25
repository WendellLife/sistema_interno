from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Auditoria, CentroCusto, Feriado, PermissaoModulo, Setor, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        ("Life Laboral", {"fields": ("setor", "matricula", "capacidade_diaria_min", "ativo_para_apontamento")}),
    )
    add_fieldsets = (
        *BaseUserAdmin.add_fieldsets,
        ("Life Laboral", {"fields": ("email", "setor", "matricula")}),
    )
    list_display = ("username", "first_name", "last_name", "setor", "matricula", "is_active")
    list_filter = ("setor", "groups", "is_active")


@admin.register(Setor)
class SetorAdmin(admin.ModelAdmin):
    list_display = ("nome", "sigla", "responsavel", "ativo")


@admin.register(CentroCusto)
class CentroCustoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "descricao", "setor", "projeto", "ativo")
    list_filter = ("setor",)


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    list_display = ("data", "nome")


@admin.register(PermissaoModulo)
class PermissaoModuloAdmin(admin.ModelAdmin):
    list_display = ("modulo", "papel", "nivel")
    list_filter = ("modulo", "papel")


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    """Somente leitura — append-only."""

    list_display = ("quando", "usuario", "acao", "objeto_tipo", "objeto_id")
    list_filter = ("acao", "objeto_tipo")
    search_fields = ("objeto_id", "acao")
    readonly_fields = [f.name for f in Auditoria._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
