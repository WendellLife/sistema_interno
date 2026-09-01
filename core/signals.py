"""Efeitos colaterais idempotentes de setup (grupos e matriz padrão) após `migrate`."""

from django.contrib.auth.models import Group

from . import papeis
from .calendario import invalidar_feriados
from .models import Feriado, PermissaoModulo


def garantir_papeis_e_matriz(**kwargs) -> None:
    for nome in papeis.TODOS:
        Group.objects.get_or_create(name=nome)
    if not PermissaoModulo.objects.exists():
        PermissaoModulo.objects.bulk_create(
            PermissaoModulo(papel=papel, modulo=modulo, nivel=nivel)
            for modulo, linha in papeis.MATRIZ_PADRAO.items()
            for papel, nivel in linha.items()
        )


def guardar_ano_do_feriado(sender, instance: Feriado, **kwargs) -> None:
    """Antes de salvar, guarda o ano que está no banco.

    Mover um feriado de ano precisa limpar os DOIS caches: sem o ano de origem, ele
    segue tratando a data antiga como feriado até o TTL expirar, e o SLA em horas
    úteis sai errado nesse meio-tempo.
    """
    anterior = (
        Feriado.objects.filter(pk=instance.pk).values_list("data", flat=True).first()
        if instance.pk
        else None
    )
    instance._ano_anterior = anterior.year if anterior else None


def limpar_cache_de_feriados(sender, instance: Feriado, **kwargs) -> None:
    """Editar o calendário tem de valer na próxima requisição, não no fim do TTL."""
    anos = {instance.data.year, instance._ano_anterior}
    for ano in filter(None, anos):
        invalidar_feriados(ano)
