import threading

import pytest
from django.db import connection

from core.numeracao import proximo_numero


@pytest.mark.django_db
def test_formato():
    assert proximo_numero("TI", 2026) == "TI-2026-0001"
    assert proximo_numero("TI", 2026) == "TI-2026-0002"
    assert proximo_numero("SOL", 2026) == "SOL-2026-0001"
    assert proximo_numero("TI", 2027) == "TI-2027-0001"


@pytest.mark.django_db(transaction=True)
def test_50_criacoes_concorrentes_sem_duplicata_nem_lacuna():
    resultados: list[str] = []
    lock = threading.Lock()

    def worker():
        try:
            n = proximo_numero("CONC", 2026)
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
    assert sorted(resultados) == [f"CONC-2026-{i:04d}" for i in range(1, 51)]
