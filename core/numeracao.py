"""Números de documento vindos de sequência do PostgreSQL (regra §11)."""

from django.db import connection
from django.utils import timezone


def proximo_numero(prefixo: str, ano: int | None = None) -> str:
    ano = ano or timezone.localdate().year
    with connection.cursor() as cur:
        cur.execute("SELECT proximo_numero(%s, %s)", [prefixo, ano])
        return cur.fetchone()[0]
