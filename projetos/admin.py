from django.contrib import admin

from .models import Projeto


@admin.register(Projeto)
class ProjetoAdmin(admin.ModelAdmin):
    list_display = ("nome", "setor_solicitante", "fase", "responsavel")
    list_filter = ("fase", "setor_solicitante")
