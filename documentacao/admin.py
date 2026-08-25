from django.contrib import admin

from .models import Documento, VersaoDocumento


class VersaoInline(admin.TabularInline):
    model = VersaoDocumento
    extra = 0
    can_delete = False
    readonly_fields = ("numero", "conteudo", "autor", "publicada_em")

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("secao", "chamado", "projeto", "versao_atual")
    inlines = [VersaoInline]


@admin.register(VersaoDocumento)
class VersaoDocumentoAdmin(admin.ModelAdmin):
    """Append-only: sem alteração nem exclusão, nem pelo admin."""

    list_display = ("documento", "numero", "autor", "publicada_em")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
