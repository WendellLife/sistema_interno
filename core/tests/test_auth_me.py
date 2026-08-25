import pytest

from core.models import PermissaoModulo
from core.permissions import invalidar_matriz

pytestmark = pytest.mark.django_db


def test_me_monta_menu_por_papel(api, usuarios):
    r = api(usuarios["colab_prd"]).get("/api/v1/auth/me/")
    assert r.status_code == 200
    assert r.data["papeis"] == ["Colaborador"]
    assert r.data["menu"] == ["tarefas", "tarefa", "almoxarifado"]
    assert r.data["permissoes"]["todos_setores"] is False

    r = api(usuarios["ger_ti"]).get("/api/v1/auth/me/")
    assert r.data["permissoes"]["todos_setores"] is True
    assert r.data["menu"] == ["painel", "tarefas", "tarefa", "projetos", "almoxarifado", "compras"]
    assert r.data["permissoes"]["aprovar_horas"] is True

    r = api(usuarios["admin"]).get("/api/v1/auth/me/")
    assert r.data["menu"][-1] == "config"


def test_matriz_alterada_muda_menu(api, usuarios):
    PermissaoModulo.objects.filter(papel="Colaborador", modulo="painel").update(nivel="V")
    invalidar_matriz()
    r = api(usuarios["colab_prd"]).get("/api/v1/auth/me/")
    assert "painel" in r.data["menu"]


def test_so_admin_edita_matriz(api, usuarios):
    p = PermissaoModulo.objects.get(papel="Colaborador", modulo="painel")
    assert api(usuarios["ger_ti"]).patch(f"/api/v1/permissoes/{p.id}/", {"nivel": "V"}).status_code == 403
    assert api(usuarios["admin"]).patch(f"/api/v1/permissoes/{p.id}/", {"nivel": "V"}).status_code == 200
