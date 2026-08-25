from rest_framework import serializers

from core.serializers import UsuarioResumoSerializer

from . import selectors
from .models import Documento, VersaoDocumento


class VersaoSerializer(serializers.ModelSerializer):
    autor = UsuarioResumoSerializer(read_only=True)

    class Meta:
        model = VersaoDocumento
        fields = ["id", "numero", "conteudo", "autor", "publicada_em", "criado_em"]
        read_only_fields = fields


class DocumentoSerializer(serializers.ModelSerializer):
    secao_label = serializers.CharField(source="get_secao_display", read_only=True)
    status = serializers.SerializerMethodField()
    resumo = serializers.SerializerMethodField()
    versao_atual = serializers.IntegerField(source="versao_atual.numero", read_only=True, default=None)
    ultima_versao = serializers.SerializerMethodField()

    class Meta:
        model = Documento
        fields = ["id", "chamado", "projeto", "secao", "secao_label", "obrigatorio",
                  "status", "resumo", "versao_atual", "ultima_versao", "atualizado_em"]  # fmt: skip
        read_only_fields = fields

    def get_status(self, obj) -> str:
        return selectors.status_documento(obj)

    def get_resumo(self, obj) -> str:
        if obj.versao_atual_id and obj.versao_atual.conteudo:
            texto = obj.versao_atual.conteudo.strip().replace("\n", " ")
            return texto[:120] + ("…" if len(texto) > 120 else "")
        return ""

    def get_ultima_versao(self, obj) -> int | None:
        versoes = list(obj.versoes.all())
        return max((v.numero for v in versoes), default=None)


class DocumentoCreateSerializer(serializers.Serializer):
    chamado = serializers.PrimaryKeyRelatedField(queryset=Documento.objects.none(), required=False, allow_null=True)
    projeto = serializers.PrimaryKeyRelatedField(queryset=Documento.objects.none(), required=False, allow_null=True)
    secao = serializers.ChoiceField(choices=Documento.Secao.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from chamados.models import Chamado
        from projetos.models import Projeto

        self.fields["chamado"].queryset = Chamado.objects.all()
        self.fields["projeto"].queryset = Projeto.objects.all()


class RascunhoSerializer(serializers.Serializer):
    conteudo = serializers.CharField()
    publicar = serializers.BooleanField(default=False)
