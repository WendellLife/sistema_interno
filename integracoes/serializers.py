from rest_framework import serializers

from almoxarifado.models import Item
from core.models import Setor, User

from .models import EventoIntegracao, SistemaExterno, Webhook


class SistemaExternoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SistemaExterno
        fields = ["id", "nome", "slug", "prefixo_chave", "escopos", "usuario_tecnico", "ips_permitidos", "ativo", "ultimo_uso"]
        read_only_fields = ["id", "prefixo_chave", "ultimo_uso"]


class WebhookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = ["id", "sistema", "url", "segredo", "eventos", "ativo"]
        extra_kwargs = {"segredo": {"write_only": True}}


class EventoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventoIntegracao
        fields = ["id", "acao", "carga", "status", "tentativas", "criado_em", "entregue_em"]


# ---- entradas genéricas (qualquer sistema) ----


class SolicitanteRef(serializers.Serializer):
    """Identifica quem pede: matrícula, e-mail ou username — o que o sistema externo tiver."""

    matricula = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    username = serializers.CharField(required=False)

    def validate(self, d):
        q = {k: v for k, v in d.items() if v}
        if not q:
            raise serializers.ValidationError("Informe matricula, email ou username.")
        user = User.objects.filter(is_active=True, **q).first()
        if not user:
            raise serializers.ValidationError("Solicitante não encontrado.")
        d["user"] = user
        return d


class ItemRef(serializers.Serializer):
    codigo = serializers.CharField(required=False)
    codigo_sankhya = serializers.CharField(required=False)
    quantidade = serializers.DecimalField(max_digits=12, decimal_places=3)

    def validate(self, d):
        item = None
        if d.get("codigo"):
            item = Item.objects.filter(codigo=d["codigo"], ativo=True).first()
        if item is None and d.get("codigo_sankhya"):
            item = Item.objects.filter(codigo_sankhya=d["codigo_sankhya"], ativo=True).first()
        if item is None:
            raise serializers.ValidationError("Item não encontrado por codigo/codigo_sankhya.")
        d["item"] = item
        return d


class SolicitacaoExternaSerializer(serializers.Serializer):
    solicitante = SolicitanteRef()
    centro_custo = serializers.CharField(required=False, allow_blank=True, help_text="código; padrão: primeiro CC ativo do setor")
    os_ref = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    urgente = serializers.BooleanField(default=False)
    origem = serializers.CharField(max_length=12, required=False, default="externo")
    itens = ItemRef(many=True)


class ChamadoExternoSerializer(serializers.Serializer):
    solicitante = SolicitanteRef()
    titulo = serializers.CharField(max_length=180)
    descricao = serializers.CharField()
    categoria = serializers.SlugField()
    prioridade = serializers.ChoiceField(choices=["critica", "alta", "media", "baixa"], default="media")


class ItemSyncSerializer(serializers.Serializer):
    """Upsert de itens por `codigo_sankhya` (ou `codigo`). Campos ausentes não são alterados."""

    codigo = serializers.CharField(max_length=20, required=False)
    codigo_sankhya = serializers.CharField(max_length=30, required=False)
    descricao = serializers.CharField(max_length=180, required=False)
    unidade = serializers.CharField(max_length=8, required=False)
    setor_dono = serializers.SlugRelatedField(slug_field="sigla", queryset=Setor.objects.all(), required=False)
    estoque_minimo = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    custo_unitario = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    ativo = serializers.BooleanField(required=False)

    def validate(self, d):
        if not d.get("codigo") and not d.get("codigo_sankhya"):
            raise serializers.ValidationError("Informe codigo ou codigo_sankhya.")
        return d
