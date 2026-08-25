from celery import shared_task
from django.core.mail import EmailMessage

from core.models import User


@shared_task(name="relatorios.gerar_export")
def gerar_export(job_id: str, user_id: int, formato: str, colunas: list, linhas: list, nome: str) -> str:
    from .export import gerar

    conteudo, mime = gerar(formato, colunas, linhas, nome)
    user = User.objects.get(pk=user_id)
    msg = EmailMessage(
        subject=f"[Sistema interno] Exportação pronta: {nome}",
        body=f"Segue o relatório {nome} ({len(linhas)} linhas). Job {job_id}.",
        to=[user.email],
    )
    msg.attach(f"{nome}.{formato}", conteudo, mime)
    msg.send(fail_silently=True)
    return job_id
