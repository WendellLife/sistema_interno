"""Camada genérica de integração: credenciais por sistema, idempotência, outbox de eventos e webhooks.
Nenhum sistema específico (WhatsApp, Sankhya…) vive aqui — eles se conectam por esta camada."""

import hashlib
import secrets

from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import TimeStampedModel

ESCOPOS = [
    ("chamados:ler", "Ler chamados"),
    ("chamados:escrever", "Abrir chamados"),
    ("almoxarifado:ler", "Ler estoque e itens"),
    ("almoxarifado:escrever", "Criar solicitações, notas e itens"),
    ("eventos:ler", "Consultar eventos (polling)"),
]


class SistemaExterno(TimeStampedModel):
    """Um sistema conectado. A chave é mostrada uma vez; só o hash fica no banco."""

    nome = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True)
    chave_hash = models.CharField(max_length=64, editable=False)
    prefixo_chave = models.CharField(max_length=8, editable=False)  # para identificar sem revelar
    escopos = ArrayField(models.CharField(max_length=30), default=list, blank=True)
    usuario_tecnico = models.ForeignKey(
        "core.User", on_delete=models.PROTECT, related_name="sistemas_externos",
        help_text="Ações feitas por este sistema são registradas em nome deste usuário.",
    )  # fmt: skip
    ips_permitidos = ArrayField(models.GenericIPAddressField(), default=list, blank=True)
    ativo = models.BooleanField(default=True)
    ultimo_uso = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "sistema externo"
        verbose_name_plural = "sistemas externos"

    def __str__(self) -> str:
        return self.nome

    @staticmethod
    def hash_de(chave: str) -> str:
        return hashlib.sha256(chave.encode()).hexdigest()

    def gerar_chave(self) -> str:
        """Gera uma chave nova, grava o hash e devolve o texto claro (uma única vez)."""
        chave = "li_" + secrets.token_urlsafe(32)
        self.chave_hash = self.hash_de(chave)
        self.prefixo_chave = chave[:8]
        return chave

    def tem_escopo(self, escopo: str) -> bool:
        return escopo in self.escopos


class ChaveIdempotencia(models.Model):
    """Resposta guardada por (sistema, Idempotency-Key). Repetir a chamada devolve a mesma resposta."""

    sistema = models.ForeignKey(SistemaExterno, on_delete=models.CASCADE)
    chave = models.CharField(max_length=128)
    caminho = models.CharField(max_length=200)
    status_http = models.PositiveSmallIntegerField()
    resposta = models.JSONField()
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["sistema", "chave"], name="uniq_idempotencia")]

    def __str__(self) -> str:
        return f"{self.sistema_id} · {self.chave}"

class Webhook(TimeStampedModel):
    """Assinatura de eventos por um sistema externo. `eventos` usa os nomes de `Auditoria.acao`
    (ex.: `chamado.entregue`, `estoque.saida`, `solicitacao.aprovar`); prefixo com `*` assina o grupo."""

    sistema = models.ForeignKey(SistemaExterno, on_delete=models.CASCADE, related_name="webhooks")
    url = models.URLField()
    segredo = models.CharField(max_length=64, help_text="HMAC-SHA256 do corpo no header X-Assinatura")
    eventos = ArrayField(models.CharField(max_length=60), default=list)
    ativo = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.sistema} → {self.url}"

    def assina(self, acao: str) -> bool:
        return any(acao == e or (e.endswith("*") and acao.startswith(e[:-1])) for e in self.eventos)


class EventoIntegracao(models.Model):
    """Outbox: cada ação auditada vira um evento durável. Entregue por webhook e consultável por polling."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        ENTREGUE = "entregue", "Entregue"
        FALHOU = "falhou", "Falhou"

    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name="entregas")
    auditoria = models.ForeignKey("core.Auditoria", on_delete=models.CASCADE, related_name="eventos")
    acao = models.CharField(max_length=60, db_index=True)
    carga = models.JSONField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDENTE, db_index=True)
    tentativas = models.PositiveSmallIntegerField(default=0)
    proxima_tentativa = models.DateTimeField(null=True, blank=True)
    ultimo_erro = models.CharField(max_length=240, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    entregue_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.tipo} → {self.webhook_id}"
