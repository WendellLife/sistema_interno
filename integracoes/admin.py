from django.contrib import admin

from .models import EventoIntegracao, SistemaExterno, Webhook


@admin.register(SistemaExterno)
class SistemaExternoAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "prefixo_chave", "escopos", "ativo", "ultimo_uso")
    readonly_fields = ("chave_hash", "prefixo_chave", "ultimo_uso")


@admin.register(Webhook)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ("sistema", "url", "eventos", "ativo")


@admin.register(EventoIntegracao)
class EventoAdmin(admin.ModelAdmin):
    list_display = ("id", "acao", "webhook", "status", "tentativas", "criado_em", "entregue_em")
    list_filter = ("status", "acao")
    readonly_fields = [f.name for f in EventoIntegracao._meta.fields]
