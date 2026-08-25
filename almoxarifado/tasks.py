from celery import shared_task
from django.utils import timezone

from .models import AlertaReposicao, Estoque, Item


@shared_task(name="almoxarifado.alertar_estoque_minimo")
def alertar_estoque_minimo(item_id: int, setor_id: int, origem: str = "minimo") -> bool:
    """Abre (ou mantém) o alerta de reposição. Idempotente: um aberto por (item, setor)."""
    item = Item.objects.get(pk=item_id)
    estoque = Estoque.objects.filter(item_id=item_id, setor_id=setor_id).first()
    saldo = estoque.saldo if estoque else 0
    if AlertaReposicao.objects.filter(item_id=item_id, setor_id=setor_id, resolvido_em__isnull=True).exists():
        return False
    AlertaReposicao.objects.create(
        item=item, setor_id=setor_id, saldo=saldo, minimo=item.estoque_minimo, origem=origem
    )
    return True


@shared_task(name="almoxarifado.resolver_alertas_repostos")
def resolver_alertas_repostos() -> int:
    """Resumo diário: fecha alertas cujo saldo voltou acima do mínimo."""
    n = 0
    for alerta in AlertaReposicao.objects.filter(resolvido_em__isnull=True).select_related("item"):
        estoque = Estoque.objects.filter(item=alerta.item, setor_id=alerta.setor_id).first()
        if estoque and estoque.saldo > alerta.item.estoque_minimo:
            alerta.resolvido_em = timezone.now()
            alerta.save(update_fields=["resolvido_em"])
            n += 1
    return n
