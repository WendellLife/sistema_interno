import django_filters as df

from . import selectors
from .models import STATUS_ABERTOS, Chamado


class ChamadoFilter(df.FilterSet):
    setor = df.NumberFilter(field_name="setor_origem_id")
    status = df.CharFilter(method="filtrar_status")
    prioridade = df.CharFilter(field_name="prioridade")
    categoria = df.CharFilter(field_name="categoria__slug")
    responsavel = df.NumberFilter(field_name="responsavel_id")
    sla_vencido = df.BooleanFilter(method="filtrar_sla_vencido")
    busca = df.CharFilter(method="filtrar_busca")

    class Meta:
        model = Chamado
        fields: list[str] = []

    def filtrar_status(self, qs, name, value):
        if value == "abertos":
            return qs.filter(status__in=STATUS_ABERTOS)
        return qs.filter(status__in=[v.strip() for v in value.split(",")])

    def filtrar_sla_vencido(self, qs, name, value):
        return qs.filter(sla_cumprido=False) if value else qs.exclude(sla_cumprido=False)

    def filtrar_busca(self, qs, name, value):
        return qs.filter(selectors.filtro_busca(value))
