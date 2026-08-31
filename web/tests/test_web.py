import pytest
from django.test import Client
from django.utils.html import strip_tags

from apontamentos.models import MOTIVOS_INICIAIS, TIPOS_INICIAIS, MotivoRetrabalho, TipoTrabalho
from chamados import services as cham
from chamados.models import Chamado

pytestmark = pytest.mark.django_db


@pytest.fixture
def tipos(db):
    for ordem, (nome, slug, exige, contabiliza) in enumerate(TIPOS_INICIAIS):
        TipoTrabalho.objects.create(nome=nome, slug=slug, exige_causa=exige, contabiliza_capacidade=contabiliza, ordem=ordem)
    for n in MOTIVOS_INICIAIS:
        MotivoRetrabalho.objects.create(nome=n)
    return {t.slug: t for t in TipoTrabalho.objects.all()}


@pytest.fixture
def web(usuarios):
    def _como(chave):
        c = Client(HTTP_HX_REQUEST="")  # HX header vazio = navegação normal
        c.force_login(usuarios[chave])
        return c

    return _como


@pytest.fixture
def chamado(usuarios, categorias):
    c = cham.abrir_chamado(solicitante=usuarios["colab_prd"], titulo="Erro na etiqueta", descricao="d",
                           categoria=categorias["dev"], prioridade="alta")  # fmt: skip
    cham.atribuir(chamado=c, responsavel=usuarios["colab_ti"], usuario=usuarios["ger_ti"])
    return c


def test_login_e_redirecionamento(usuarios):
    c = Client()
    assert c.get("/tarefas/").status_code == 302
    r = c.post("/entrar/", {"username": "colab_prd", "password": "x"})
    assert r.status_code == 302 and r["Location"] == "/tarefas/"
    assert c.get("/tarefas/").status_code == 200


def test_menu_vem_da_matriz(web):
    html = web("colab_prd").get("/tarefas/").content.decode()
    assert "Central de tarefas" in html and "Painel de indicadores" not in html and "SLA e permissões" not in html
    html = web("admin").get("/tarefas/").content.decode()
    assert "Painel de indicadores" in html and "SLA e permissões" in html


def test_central_lista_e_filtra_por_escopo(web, chamado, usuarios, categorias):
    outro = cham.abrir_chamado(solicitante=usuarios["colab_man"], titulo="Outro setor", descricao="d",
                               categoria=categorias["suporte"], prioridade="baixa")  # fmt: skip
    html = web("colab_prd").get("/tarefas/").content.decode()
    assert chamado.numero in html and outro.numero not in html
    assert "1 chamado aberto" in html
    html = web("ger_ti").get("/tarefas/").content.decode()
    assert chamado.numero in html and outro.numero in html
    # partial HTMX com filtro
    r = web("ger_ti").get("/tarefas/?prioridade=baixa", HTTP_HX_REQUEST="true")
    assert r.status_code == 200 and outro.numero in r.content.decode() and chamado.numero not in r.content.decode()
    assert "<html" not in r.content.decode()


def test_novo_chamado_redireciona_para_tarefa(web, categorias):
    r = web("colab_prd").post("/tarefas/novo/", {"titulo": "Novo", "descricao": "d", "categoria": categorias["suporte"].id, "prioridade": "media"})
    assert r.status_code == 204 and r["HX-Redirect"].startswith("/tarefas/")
    c = Chamado.objects.get(titulo="Novo")
    assert c.setor_origem.sigla == "PRD"
    # Compras tem só leitura em tarefas → 404 (matriz)
    r = web("compras").post("/tarefas/novo/", {"titulo": "x", "descricao": "d", "categoria": categorias["suporte"].id, "prioridade": "media"})
    assert r.status_code == 404


def test_tarefa_fora_do_escopo_404(web, chamado):
    assert web("colab_ti").get(f"/tarefas/{chamado.pk}/").status_code == 200  # responsável
    assert web("colab_man").get(f"/tarefas/{chamado.pk}/").status_code == 404


def test_cronometro_no_card(web, chamado, tipos, usuarios):
    cli = web("colab_ti")
    r = cli.post(f"/tarefas/{chamado.pk}/cronometro/", {"acao": "iniciar", "tipo": tipos["desenvolvimento"].id})
    assert r.status_code == 200 and 'class="dot ativo"' in r.content.decode()
    r = cli.post(f"/tarefas/{chamado.pk}/cronometro/", {"acao": "iniciar", "tipo": tipos["testes"].id})
    assert "Desenvolvimento pausado" in r.content.decode()
    # retrabalho sem causa: card volta com o erro no lugar, status 400
    r = cli.post(f"/tarefas/{chamado.pk}/cronometro/", {"acao": "iniciar", "tipo": tipos["retrabalho"].id})
    assert r.status_code == 400 and "Obrigatório para retrabalho" in r.content.decode()
    r = cli.post(f"/tarefas/{chamado.pk}/cronometro/", {"acao": "parar"})
    assert r.status_code == 200 and "parado" in r.content.decode()
    estado = cli.get("/cronometro/estado/").json()
    assert estado["ativo"] is False


def test_lancamento_manual_previa_e_conflito(web, chamado, tipos):
    cli = web("colab_ti")
    base = {"tipo": tipos["analise"].id, "data": "2026-08-24", "inicio": "08:00", "fim": "12:00"}
    assert cli.post(f"/tarefas/{chamado.pk}/lancamento/", base).status_code == 200
    r = cli.get(f"/tarefas/{chamado.pk}/lancamento/previa/", {**base, "inicio": "11:00", "fim": "13:00"})
    assert "Conflita com Análise 08:00–12:00" in r.content.decode()
    r = cli.post(f"/tarefas/{chamado.pk}/lancamento/", {**base, "inicio": "11:00", "fim": "13:00"})
    assert r.status_code == 400 and "Conflita com apontamento de Análise" in r.content.decode()
    r = cli.get(f"/tarefas/{chamado.pk}/lancamento/previa/", {**base, "inicio": "13:00", "fim": "18:00"})
    assert "exigirá aprovação do gerente" in r.content.decode()


def test_entrega_bloqueada_vira_modal_com_atalhos(web, chamado, usuarios):
    for p in ("triagem", "fila", "execucao", "testes"):
        cham.transicionar(chamado=chamado, para=p, usuario=usuarios["ger_ti"])
    r = web("colab_ti").post(f"/tarefas/{chamado.pk}/transicao/", {"status": "entregue"})
    html = r.content.decode()
    assert r.status_code == 409 and "Entrega bloqueada" in html and "Como foi testado" in html
    assert html.count(f"/tarefas/{chamado.pk}/documentacao/") == 4


def test_editor_publica_e_libera_entrega(web, chamado, usuarios):
    cli = web("colab_ti")
    r = cli.get(f"/tarefas/{chamado.pk}/documentacao/teste/")
    assert r.status_code == 200 and "Como foi testado" in r.content.decode()
    r = cli.post(f"/tarefas/{chamado.pk}/documentacao/teste/", {"conteudo": "Testado em homologação", "acao": "publicar"})
    assert r.status_code == 204 and r["HX-Refresh"] == "true"
    for secao in ("contexto", "regra", "solucao"):
        cli.post(f"/tarefas/{chamado.pk}/documentacao/{secao}/", {"conteudo": "ok", "acao": "publicar"})
    for p in ("triagem", "fila", "execucao", "testes"):
        cham.transicionar(chamado=chamado, para=p, usuario=usuarios["ger_ti"])
    r = cli.post(f"/tarefas/{chamado.pk}/transicao/", {"status": "entregue"})
    assert r.status_code == 204
    chamado.refresh_from_db()
    assert chamado.status == "entregue"
    # gerente do setor só lê documentação
    assert web("ger_prd").post(f"/tarefas/{chamado.pk}/documentacao/teste/", {"conteudo": "x"}).status_code == 404


def test_comentario_interno_e_transicao_invalida(web, chamado):
    r = web("colab_ti").post(f"/tarefas/{chamado.pk}/comentar/", {"texto": "nota", "interno": "on"})
    assert "Interno" in r.content.decode()
    assert "nota" not in web("colab_prd").get(f"/tarefas/{chamado.pk}/").content.decode()
    r = web("colab_ti").post(f"/tarefas/{chamado.pk}/transicao/", {"status": "entregue"})
    assert r.status_code == 409 and "Siga a ordem do fluxo" in r.content.decode()


def test_busca_e_tarefa_atual(web, chamado):
    r = web("colab_ti").get("/busca/?q=etiqueta")
    assert chamado.numero in r.content.decode()
    assert web("colab_ti").get("/tarefa/")["Location"] == f"/tarefas/{chamado.pk}/"


def test_painel_renderiza_kpis_e_respeita_matriz(web, chamado, usuarios, tipos):
    from datetime import timedelta

    from django.utils import timezone

    from apontamentos import services as ap

    ini = timezone.localtime(timezone.now()).replace(hour=8, minute=0, second=0, microsecond=0)
    ap.criar_apontamento(usuario=usuarios["colab_ti"], tipo=tipos["desenvolvimento"], chamado=chamado, inicio=ini, fim=ini + timedelta(hours=3))
    r = web("ger_ti").get("/painel/")
    html = r.content.decode()
    assert r.status_code == 200
    assert "Horas apontadas no período" in html and "3,0h" in html
    assert "Nada apontado neste período" not in html.split("Retrabalho por motivo")[0]  # card de horas tem dados
    assert "Nada apontado neste período" in html  # retrabalho por motivo vazio: card fica, não some
    assert web("colab_prd").get("/painel/").status_code == 404
    r = web("ger_ti").get("/painel/?de=2020-01-01&ate=2020-01-31")
    assert "0,0h" in r.content.decode()


@pytest.fixture
def almox_dados(setores, usuarios):
    from decimal import Decimal

    from almoxarifado import services as almox
    from almoxarifado.models import Item
    from core.models import CentroCusto

    cc = CentroCusto.objects.create(codigo="2002", descricao="Operação Produção", setor=setores["PRD"])
    parafuso = Item.objects.create(codigo="MRO-4471", descricao="Parafuso M8", unidade="UN", setor_dono=setores["PRD"], estoque_minimo=5, custo_unitario=Decimal("1.50"))
    luva = Item.objects.create(codigo="EPI-0012", descricao="Luva nitrílica", unidade="PC", setor_dono=setores["PRD"], estoque_minimo=20, custo_unitario=Decimal("4.00"))
    almox.registrar_movimento(item=parafuso, setor=setores["PRD"], tipo="entrada", quantidade=10, usuario=usuarios["admin"])
    almox.registrar_movimento(item=luva, setor=setores["PRD"], tipo="entrada", quantidade=8, usuario=usuarios["admin"])
    return {"cc": cc, "parafuso": parafuso, "luva": luva}


def test_almox_tela_kpis_e_situacoes(web, almox_dados):
    html = web("colab_prd").get("/almoxarifado/").content.decode()
    assert "Estoque do setor" in html and "CC 2002" in html
    assert "Abaixo do mínimo" in html  # luva 8 <= 20
    assert 'class="chip chip-ok">OK' in html  # parafuso 10 > 5
    # Colaborador solicita, não faz NF nem inventário
    assert "Solicitar material" in html and "Entrada por nota fiscal" not in html
    html = web("compras").get(f"/almoxarifado/?setor={almox_dados['cc'].setor_id}").content.decode()
    assert "Entrada por nota fiscal" in html and "Inventário cíclico" in html


def test_almox_solicitar_aprovar_atender(web, almox_dados, setores):
    from almoxarifado.models import Solicitacao

    r = web("colab_prd").post("/almoxarifado/solicitar/", {"centro_custo": almox_dados["cc"].id, "os_ref": "OS-1",
                                                           "item": [almox_dados["parafuso"].id], "quantidade": ["4"]})  # fmt: skip
    assert r.status_code == 204 and r["HX-Refresh"] == "true"
    sol = Solicitacao.objects.get()
    assert sol.status == "aberta" and sol.setor == setores["PRD"]
    html = web("ger_prd").get("/almoxarifado/").content.decode()
    assert f"/almoxarifado/solicitacoes/{sol.pk}/aprovar/" in html
    assert web("ger_prd").post(f"/almoxarifado/solicitacoes/{sol.pk}/aprovar/").status_code == 204
    assert web("resp_prd").post(f"/almoxarifado/solicitacoes/{sol.pk}/atender/").status_code == 204
    sol.refresh_from_db()
    assert sol.status == "atendida"
    # sem centro de custo → erro em modal, status 400
    r = web("colab_prd").post("/almoxarifado/solicitar/", {"item": [almox_dados["parafuso"].id], "quantidade": ["1"]})
    assert r.status_code == 400 and "Centro de custo" in r.content.decode()


def test_almox_saida_sem_referencia_e_saldo_insuficiente_viram_modal(web, almox_dados):
    cli = web("resp_prd")
    r = cli.post("/almoxarifado/saida/", {"item": almox_dados["parafuso"].id, "quantidade": "1"})
    assert r.status_code == 400 and "centro de custo, chamado, projeto ou OS" in r.content.decode()
    r = cli.post("/almoxarifado/saida/", {"item": almox_dados["parafuso"].id, "quantidade": "99", "os_ref": "OS-2"})
    assert r.status_code == 409 and "Saldo insuficiente" in r.content.decode()


def test_almox_transferencia_previa_e_execucao(web, almox_dados, setores):
    cli = web("resp_prd")
    r = cli.get("/almoxarifado/transferir/previa/", {"item": almox_dados["parafuso"].id, "quantidade": "8"})
    assert "ficará abaixo do mínimo (5 UN)" in r.content.decode()
    r = cli.post("/almoxarifado/transferir/", {"item": almox_dados["parafuso"].id, "quantidade": "8", "setor_destino": setores["MAN"].id, "motivo": "linha 2"})
    assert r.status_code == 204
    from almoxarifado import selectors

    assert selectors.saldo(almox_dados["parafuso"], setores["MAN"]) == 8


def test_almox_nota_e_inventario(web, almox_dados, setores):
    cli = web("compras")
    q = f"?setor={setores['PRD'].id}"
    r = cli.post(f"/almoxarifado/nota/{q}", {"numero": "123", "fornecedor": "F", "emissao": "2026-08-20", "valor_total": "15.00",
                                           "item": [almox_dados["parafuso"].id], "pedida": ["10"], "recebida": ["10"], "custo": ["1.50"], "divergencia": [""]})  # fmt: skip
    assert r.status_code == 204
    from almoxarifado import selectors
    from almoxarifado.models import Inventario

    assert selectors.saldo(almox_dados["parafuso"], setores["PRD"]) == 20
    r = cli.get(f"/almoxarifado/inventario/{q}")
    assert r.status_code == 200 and "rodada #" in r.content.decode() and Inventario.objects.filter(status="aberto").count() == 1
    r = cli.post(f"/almoxarifado/inventario/{q}", {"acao": "fechar", "item": [almox_dados["parafuso"].id, almox_dados["luva"].id], "contado": ["18", ""]})
    # O número vem em <b>: comparar o HTML cru nunca casaria com "1 divergência".
    texto = strip_tags(r.content.decode())
    assert r.status_code == 200 and "1 divergência" in texto and "R$ 3,00" in texto
    assert selectors.saldo(almox_dados["parafuso"], setores["PRD"]) == 18
    assert selectors.saldo(almox_dados["luva"], setores["PRD"]) == 8  # sem contagem: ignorado
    # colaborador não abre inventário
    assert web("colab_prd").get("/almoxarifado/inventario/").status_code == 404


def test_almox_qr(web, almox_dados):
    r = web("colab_prd").get("/almoxarifado/qr/MRO-4471/")
    html = r.content.decode()
    assert r.status_code == 200 and "Parafuso M8" in html and "Saída rápida" in html
    r = web("colab_prd").get("/almoxarifado/qr/?codigo=NADA", HTTP_HX_REQUEST="true")
    assert "não encontrado" in r.content.decode() and "<html" not in r.content.decode()
    r = web("colab_prd").get("/almoxarifado/itens/?q=luva")
    assert "EPI-0012" in r.content.decode()


def test_projetos_kanban_novo_mover_e_historico(web, usuarios, setores):
    from projetos.models import Projeto

    ger = web("ger_ti")
    r = ger.post("/projetos/novo/", {"nome": "Dashboard OEE", "setor_solicitante": setores["MAN"].id, "patrocinador": usuarios["colab_man"].id,
                                     "responsavel": usuarios["colab_ti"].id, "horas_estimadas": "40", "fim_previsto": "2026-12-01"})  # fmt: skip
    assert r.status_code == 204
    p = Projeto.objects.get(nome="Dashboard OEE")
    html = ger.get("/projetos/").content.decode()
    assert "Dashboard OEE" in html and "Ideia" in html and "40h /" in html
    assert ger.post(f"/projetos/{p.pk}/mover/", {"fase": "analise"}).status_code == 204
    # concluir sem data → modal pedindo data e situação (400), não avança
    r = ger.post(f"/projetos/{p.pk}/mover/", {"fase": "cancelado"})
    assert r.status_code == 400 and "Encerrar exige data" in r.content.decode()
    assert ger.post(f"/projetos/{p.pk}/mover/", {"fase": "cancelado", "encerrado_em": "2026-08-24", "situacao_final": "Pedido do setor"}).status_code == 204
    html = ger.get("/projetos/historico/?ano=2026").content.decode()
    assert "Dashboard OEE" in html and "Pedido do setor" in html and "Cancelados" in html
    # colaborador não tem o módulo; gerente de PRD vê só PRD (lista vazia) e não cria
    assert web("colab_prd").get("/projetos/").status_code == 404
    assert "Dashboard OEE" not in web("ger_prd").get("/projetos/historico/?ano=2026").content.decode()
    assert web("ger_prd").post("/projetos/novo/", {"nome": "x"}).status_code == 404


def test_compras_tela_e_cotacao(web, almox_dados, setores, usuarios):
    from almoxarifado.models import Cotacao

    cli = web("compras")
    html = cli.get("/compras/").content.decode()
    assert "Consumo e ruptura por setor" in html and "Fila de reposição" in html and "Produção" in html
    r = cli.post("/compras/cotacoes/nova/", {"item": almox_dados["luva"].id, "quantidade": "200", "prazo_resposta": "2026-09-01"})
    assert r.status_code == 204
    cot = Cotacao.objects.get()
    assert cli.post(f"/compras/cotacoes/{cot.pk}/proposta/", {"fornecedor": "A", "valor_unitario": "3.90", "prazo_entrega_dias": "5"}).status_code == 204
    assert cli.post(f"/compras/cotacoes/{cot.pk}/proposta/", {"fornecedor": "B", "valor_unitario": "3.50", "prazo_entrega_dias": "12"}).status_code == 204
    html = cli.get("/compras/").content.decode()
    assert "Escolher" in html and html.count("Escolher") >= 2
    prop = cot.propostas.get(fornecedor="B")
    assert cli.post(f"/compras/propostas/{prop.pk}/escolher/").status_code == 204
    cot.refresh_from_db()
    assert cot.status == "fechada"
    # Gerente de TI vê Compras (matriz V) mas não abre cotação
    assert web("ger_ti").get("/compras/").status_code == 200
    assert web("ger_ti").post("/compras/cotacoes/nova/", {"item": almox_dados["luva"].id}).status_code == 404
    assert web("colab_prd").get("/compras/").status_code == 404


def test_config_sla_simulacao_e_matriz(web, usuarios, categorias, chamado):
    from core.models import PermissaoModulo
    from core.permissions import invalidar_matriz

    adm = web("admin")
    html = adm.get("/config/").content.decode()
    assert "SLA por prioridade" in html and "Matriz de permissões" in html and "linha parada" in html
    sim = adm.get("/config/sla/simular/", {"critica": 1, "alta": 1, "media": 1, "baixa": 1}).json()
    assert sim["total"] == 1  # chamado alta recém-aberto: 1h ainda não passou
    sim = adm.get("/config/sla/simular/", {"critica": 0, "alta": 0, "media": 0, "baixa": 0}).json()
    assert sim["no_prazo"] == 0 and sim["percentual"] == 0
    assert adm.post("/config/sla/", {"critica": 2, "alta": 12, "media": 48, "baixa": 72}).status_code == 204
    from chamados.models import RegraSLA

    assert set(RegraSLA.objects.filter(prioridade="alta").values_list("horas_uteis", flat=True)) == {12}
    # célula: V → E → - → V
    r = adm.post("/config/permissao/", {"papel": "Compras", "modulo": "tarefas"})
    assert r.status_code == 200 and "editar" in r.content.decode()
    assert PermissaoModulo.objects.get(papel="Compras", modulo="tarefas").nivel == "E"
    adm.post("/config/permissao/", {"papel": "Compras", "modulo": "tarefas"})
    assert PermissaoModulo.objects.get(papel="Compras", modulo="tarefas").nivel == "-"
    invalidar_matriz()
    assert web("compras").get("/tarefas/").status_code == 404  # o menu/rota já respeita
    assert adm.post("/config/motivo/novo/", {"nome": "Dado errado na origem"}).status_code == 204
    assert web("ger_ti").get("/config/").status_code == 404


def test_historico_de_mudancas(web, chamado):
    r = web("ger_ti").get(f"/historico/?objeto=chamados.chamado:{chamado.pk}")
    html = r.content.decode()
    assert r.status_code == 200 and "chamado.abrir" in html and "chamado.atribuir" in html
    assert web("colab_prd").get("/historico/").status_code == 404

def test_sem_dependencia_de_cdn_externo(web):
    """A interface inteira depende de HTMX e Alpine: se vierem de CDN, uma rede que
    bloqueie o domínio deixa tudo inerte sem nenhum erro visível ao usuário."""
    html = web("colab_prd").get("/tarefas/").content.decode()
    assert "unpkg.com" not in html and "cdn.jsdelivr" not in html and "cdnjs" not in html
    assert "/static/js/vendor/htmx-" in html
    assert "/static/js/vendor/alpine-" in html


def test_troca_de_filtro_tem_estado_de_carregamento(web):
    """05 §2: nenhuma troca de partial acontece em silêncio."""
    html = web("colab_prd").get("/tarefas/").content.decode()
    assert 'hx-indicator="#tabela"' in html
    assert 'id="tabela" class="recarregavel"' in html
