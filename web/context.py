"""Contexto do shell: menu (decidido em core.serializers.montar_me), badges e cronômetro ativo."""

from apontamentos import services as ap_services
from chamados.models import STATUS_ABERTOS, Chamado
from core.serializers import montar_me

ROTULOS = {
    "painel": ("Gestão", "Painel de indicadores", "web:painel"),
    "tarefas": ("", "Central de tarefas", "web:tarefas"),
    "tarefa": ("", "Tarefa em andamento", "web:tarefa_atual"),
    "projetos": ("Portfólio", "Projetos de TI", "web:projetos"),
    "almoxarifado": ("Materiais", "Almoxarifado", "web:almoxarifado"),
    "compras": ("", "Compras", "web:compras"),
    "config": ("Administração", "SLA e permissões", "web:config"),
}


def shell(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    me = montar_me(user)
    ativo = ap_services.cronometro_aberto(user)
    badges = {"tarefas": Chamado.objects.filter(status__in=STATUS_ABERTOS).count() if me["permissoes"]["todos_setores"]
              else Chamado.objects.filter(status__in=STATUS_ABERTOS, setor_origem=user.setor).count()}  # fmt: skip
    try:
        from almoxarifado.models import AlertaReposicao

        badges["almoxarifado"] = AlertaReposicao.objects.filter(resolvido_em__isnull=True).count()
    except Exception:  # noqa: BLE001
        badges["almoxarifado"] = 0
    menu, grupo_atual = [], None
    for chave in me["menu"]:
        grupo, rotulo, rota = ROTULOS[chave]
        menu.append({"chave": chave, "grupo": grupo if grupo != grupo_atual else "", "rotulo": rotulo,
                     "rota": rota, "badge": badges.get(chave)})  # fmt: skip
        grupo_atual = grupo or grupo_atual
    rota = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
    ativa = {"painel": "painel", "tarefas": "tarefas", "abrir_chamado": "tarefas", "tarefa": "tarefa", "tarefa_atual": "tarefa",
             "projetos": "projetos", "projetos_historico": "projetos", "compras": "compras", "config": "config", "historico": "config"}  # fmt: skip
    secao = ativa.get(rota) or ("almoxarifado" if rota.startswith("almox") else "")
    return {"me": me, "menu": menu, "cronometro_ativo": ativo, "papel_principal": (me["papeis"] or ["—"])[0], "secao_ativa": secao}
