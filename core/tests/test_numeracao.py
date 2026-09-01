import threading
from uuid import uuid4

import pytest
from django.db import connection

from core.numeracao import proximo_numero


def prefixo_novo() -> str:
    """Prefixo inédito a cada execução.

    Sequência do PostgreSQL não faz rollback e sobrevive ao `--reuse-db` (que é o padrão
    do projeto). Fixar o prefixo faria estes testes passarem só em banco recém-criado e
    falharem da segunda rodada em diante — sem que nada tivesse quebrado.
    """
    return f"T{uuid4().hex[:8].upper()}"


@pytest.mark.django_db
def test_formato():
    p = prefixo_novo()
    assert proximo_numero(p, 2026) == f"{p}-2026-0001"
    assert proximo_numero(p, 2026) == f"{p}-2026-0002"
    # prefixo e ano têm sequências próprias, cada uma começando do 1
    outro = prefixo_novo()
    assert proximo_numero(outro, 2026) == f"{outro}-2026-0001"
    assert proximo_numero(p, 2027) == f"{p}-2027-0001"


@pytest.mark.django_db(transaction=True)
def test_50_criacoes_concorrentes_sem_duplicata_nem_lacuna():
    p = prefixo_novo()
    resultados: list[str] = []
    lock = threading.Lock()

    def worker():
        try:
            n = proximo_numero(p, 2026)
            with lock:
                resultados.append(n)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(resultados)) == 50
    assert sorted(resultados) == [f"{p}-2026-{i:04d}" for i in range(1, 51)]
