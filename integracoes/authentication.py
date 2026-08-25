"""`Authorization: Api-Key <chave>` → autentica como o usuário técnico do sistema externo."""

from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from .models import SistemaExterno


class ChaveDeSistemaAuthentication(BaseAuthentication):
    keyword = "Api-Key"

    def authenticate(self, request):
        partes = get_authorization_header(request).split()
        if not partes or partes[0].decode().lower() != self.keyword.lower():
            return None
        if len(partes) != 2:
            raise exceptions.AuthenticationFailed("Cabeçalho Api-Key inválido.")
        chave = partes[1].decode()
        sistema = SistemaExterno.objects.select_related("usuario_tecnico").filter(
            chave_hash=SistemaExterno.hash_de(chave), ativo=True
        ).first()
        if not sistema:
            raise exceptions.AuthenticationFailed("Chave inválida ou inativa.")
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
        if sistema.ips_permitidos and ip not in sistema.ips_permitidos:
            raise exceptions.AuthenticationFailed("IP não autorizado para esta chave.")
        SistemaExterno.objects.filter(pk=sistema.pk).update(ultimo_uso=timezone.now())
        request.sistema_externo = sistema
        return sistema.usuario_tecnico, sistema

    def authenticate_header(self, request):
        return self.keyword
