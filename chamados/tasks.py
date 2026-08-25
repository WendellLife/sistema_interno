from celery import shared_task

from . import services


@shared_task(name="chamados.verificar_sla")
def verificar_sla() -> int:
    """Roda a cada 15 min: marca vencidos sem fechar o chamado (regra §6)."""
    return services.marcar_slas_vencidos()
