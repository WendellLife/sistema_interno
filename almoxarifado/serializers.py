from rest_framework import serializers

from core.serializers import SetorSerializer, UsuarioResumoSerializer

from .models import (
    ContagemInventario,
    Cotacao,
    Estoque,
    Inventario,
    Item,
    ItemNotaFiscal,
    ItemSolicitacao,
    Movimento,
    NotaFiscal,
    PropostaCotacao,
    Solicitacao,
    Transferencia,
)


class ItemSerializer(serializers.ModelSerializer):
    saldo = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, default=None)
    abaixo_minimo = serializers.BooleanField(read_only=True, default=None)
    setor_dono_sigla = serializers.CharField(source="setor_dono.sigla", read_only=True)

    class Meta:
        model = Item
        fields = ["id", "codigo", "descricao", "unidade", "setor_dono", "setor_dono_sigla", "estoque_minimo",
                  "custo_unitario", "codigo_sankhya", "ativo", "saldo", "abaixo_minimo"]  # fmt: skip


class EstoqueSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)

    class Meta:
        model = Estoque
        fields = ["id", "item", "setor", "saldo", "atualizado_em"]


class MovimentoSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    setor = SetorSerializer(read_only=True)
    usuario = UsuarioResumoSerializer(read_only=True)
    tipo_label = serializers.CharField(source="get_tipo_display", read_only=True)
    consumo_geral = serializers.BooleanField(read_only=True)

    class Meta:
        model = Movimento
        fields = ["id", "item", "setor", "tipo", "tipo_label", "quantidade", "sinal", "saldo_apos",
                  "centro_custo", "chamado", "projeto", "os_ref", "nota_fiscal", "solicitacao",
                  "inventario", "transferencia", "usuario", "justificativa", "consumo_geral", "criado_em"]  # fmt: skip
        read_only_fields = fields


class MovimentoCreateSerializer(serializers.Serializer):
    """Apenas entrada avulsa, saída e ajuste. Transferência, NF e inventário têm endpoint próprio."""

    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(ativo=True))
    setor = serializers.PrimaryKeyRelatedField(queryset=Item.objects.none())
    tipo = serializers.ChoiceField(choices=[Movimento.Tipo.ENTRADA, Movimento.Tipo.SAIDA, Movimento.Tipo.AJUSTE])
    quantidade = serializers.DecimalField(max_digits=12, decimal_places=3)
    sinal = serializers.ChoiceField(choices=[1, -1], required=False, default=1)
    centro_custo = serializers.PrimaryKeyRelatedField(queryset=Item.objects.none(), required=False, allow_null=True)
    chamado = serializers.PrimaryKeyRelatedField(queryset=Item.objects.none(), required=False, allow_null=True)
    projeto = serializers.PrimaryKeyRelatedField(queryset=Item.objects.none(), required=False, allow_null=True)
    os_ref = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    justificativa = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from chamados.models import Chamado
        from core.models import CentroCusto, Setor
        from projetos.models import Projeto

        self.fields["setor"].queryset = Setor.objects.filter(ativo=True)
        self.fields["centro_custo"].queryset = CentroCusto.objects.filter(ativo=True)
        self.fields["chamado"].queryset = Chamado.objects.all()
        self.fields["projeto"].queryset = Projeto.objects.all()


class ItemSolicitacaoSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    pendente = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)

    class Meta:
        model = ItemSolicitacao
        fields = ["id", "item", "quantidade", "quantidade_atendida", "pendente"]


class SolicitacaoSerializer(serializers.ModelSerializer):
    itens = ItemSolicitacaoSerializer(many=True, read_only=True)
    setor = SetorSerializer(read_only=True)
    solicitante = UsuarioResumoSerializer(read_only=True)
    aprovada_por = UsuarioResumoSerializer(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Solicitacao
        fields = ["id", "numero", "setor", "solicitante", "centro_custo", "os_ref", "urgente", "status",
                  "status_label", "aprovada_por", "aprovada_em", "motivo_negacao", "origem", "itens", "criado_em"]  # fmt: skip
        read_only_fields = fields


class ItemSolicitacaoEntrada(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(ativo=True))
    quantidade = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)


class SolicitacaoCreateSerializer(serializers.Serializer):
    centro_custo = serializers.PrimaryKeyRelatedField(queryset=Item.objects.none())
    os_ref = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    urgente = serializers.BooleanField(default=False)
    itens = ItemSolicitacaoEntrada(many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import CentroCusto

        self.fields["centro_custo"].queryset = CentroCusto.objects.filter(ativo=True)


class AtenderSerializer(serializers.Serializer):
    """`quantidades`: {item_id: qtd}. Vazio/ausente = atender tudo o que falta."""

    quantidades = serializers.DictField(
        child=serializers.DecimalField(max_digits=12, decimal_places=3), required=False, default=dict
    )


class NegarSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=240)


class ItemNotaFiscalSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)

    class Meta:
        model = ItemNotaFiscal
        fields = ["id", "item", "quantidade_pedida", "quantidade_recebida", "custo_unitario", "divergencia"]


class NotaFiscalSerializer(serializers.ModelSerializer):
    itens = ItemNotaFiscalSerializer(many=True, read_only=True)
    conferida_por = UsuarioResumoSerializer(read_only=True)

    class Meta:
        model = NotaFiscal
        fields = ["id", "numero", "serie", "fornecedor", "cnpj", "emissao", "valor_total", "setor",
                  "arquivo", "conferida_por", "itens", "criado_em"]  # fmt: skip
        read_only_fields = fields


class ItemNotaEntrada(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(ativo=True))
    quantidade_pedida = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    quantidade_recebida = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    custo_unitario = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    divergencia = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")


class NotaFiscalCreateSerializer(serializers.Serializer):
    numero = serializers.CharField(max_length=20)
    serie = serializers.CharField(max_length=6, required=False, allow_blank=True, default="")
    fornecedor = serializers.CharField(max_length=140)
    cnpj = serializers.CharField(max_length=18, required=False, allow_blank=True, default="")
    emissao = serializers.DateField()
    valor_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    setor = serializers.PrimaryKeyRelatedField(queryset=Item.objects.none())
    itens = ItemNotaEntrada(many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import Setor

        self.fields["setor"].queryset = Setor.objects.filter(ativo=True)


class TransferenciaSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    setor_origem = SetorSerializer(read_only=True)
    setor_destino = SetorSerializer(read_only=True)

    class Meta:
        model = Transferencia
        fields = ["id", "item", "setor_origem", "setor_destino", "quantidade", "motivo", "fura_minimo_origem", "criado_em"]
        read_only_fields = fields


class TransferenciaCreateSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(ativo=True))
    setor_origem = serializers.PrimaryKeyRelatedField(queryset=Item.objects.none())
    setor_destino = serializers.PrimaryKeyRelatedField(queryset=Item.objects.none())
    quantidade = serializers.DecimalField(max_digits=12, decimal_places=3)
    motivo = serializers.CharField(max_length=180)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import Setor

        for f in ("setor_origem", "setor_destino"):
            self.fields[f].queryset = Setor.objects.filter(ativo=True)


class ContagemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    divergencia = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)

    class Meta:
        model = ContagemInventario
        fields = ["id", "item", "saldo_sistema", "saldo_contado", "divergencia"]


class InventarioSerializer(serializers.ModelSerializer):
    contagens = ContagemSerializer(many=True, read_only=True)
    setor = SetorSerializer(read_only=True)
    responsavel = UsuarioResumoSerializer(read_only=True)

    class Meta:
        model = Inventario
        fields = ["id", "setor", "responsavel", "status", "fechado_em", "divergencias", "impacto_valor",
                  "contagens", "criado_em"]  # fmt: skip
        read_only_fields = fields


class InventarioCreateSerializer(serializers.Serializer):
    setor = serializers.PrimaryKeyRelatedField(queryset=Item.objects.none())
    itens = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), many=True, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import Setor

        self.fields["setor"].queryset = Setor.objects.filter(ativo=True)


class ContagensEntradaSerializer(serializers.Serializer):
    contagens = serializers.DictField(
        child=serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0)
    )


class PropostaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropostaCotacao
        fields = ["id", "cotacao", "fornecedor", "valor_unitario", "prazo_entrega_dias", "escolhida"]
        read_only_fields = ["id", "cotacao", "escolhida"]


class CotacaoSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    propostas = PropostaSerializer(many=True, read_only=True)

    class Meta:
        model = Cotacao
        fields = ["id", "item", "quantidade", "prazo_resposta", "status", "propostas", "criado_em"]
        read_only_fields = fields


class CotacaoCreateSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(ativo=True))
    quantidade = serializers.DecimalField(max_digits=12, decimal_places=3)
    prazo_resposta = serializers.DateField()
