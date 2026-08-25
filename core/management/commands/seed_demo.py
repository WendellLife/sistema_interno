"""Seed de demonstração replicando os números do protótipo (F1: setores, papéis, usuários,
categorias, SLA, projetos e 34 chamados abertos). Idempotente — pode rodar mais de uma vez."""

import random
from datetime import date, timedelta

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apontamentos import services as ap_services
from apontamentos.models import MOTIVOS_INICIAIS, TIPOS_INICIAIS, Apontamento, MotivoRetrabalho, TipoTrabalho
from chamados import services as chamados_services
from chamados.models import Categoria, Chamado, RegraSLA
from core import papeis
from core.models import CentroCusto, Setor, User
from core.permissions import invalidar_papeis
from projetos.models import Projeto

SETORES = [
    ("Manutenção", "MAN"), ("Produção", "PRD"), ("Expedição", "EXP"), ("Qualidade", "QLD"),
    ("Cobrança", "COB"), ("Financeiro", "FIN"), ("Marketing", "MKT"), ("Comercial", "COM"),
    ("RH", "RH"), ("Compras", "CMP"), ("TI", "TI"),
]  # fmt: skip

CATEGORIAS = [
    ("Desenvolvimento", "desenvolvimento", True),
    ("Regra de negócio", "regra_negocio", True),
    ("Suporte", "suporte", False),
    ("Acesso", "acesso", False),
    ("Infraestrutura", "infraestrutura", False),
    ("Relatório", "relatorio", False),
    ("Integração", "integracao", False),
    ("Melhoria", "melhoria", False),
]

NOMES = [
    "Diego Martins", "Ana Souza", "Bruno Lima", "Carla Mendes", "Eduardo Rocha", "Fernanda Alves",
    "Gustavo Pereira", "Helena Costa", "Igor Santos", "Juliana Ribeiro", "Kaique Moraes",
    "Larissa Nunes", "Marcos Vieira", "Natália Freitas", "Otávio Cardoso", "Patrícia Duarte",
    "Rafael Teixeira", "Sabrina Lopes", "Thiago Barbosa", "Vanessa Castro", "William Dias",
    "Yasmin Correia", "André Gomes", "Beatriz Pinto", "Caio Monteiro", "Débora Araújo",
    "Elias Fonseca", "Flávia Ramos", "Henrique Melo", "Isabela Cunha", "João Batista",
    "Karen Xavier", "Leonardo Silva", "Mariana Azevedo", "Nícolas Reis", "Olívia Campos",
    "Paulo Macedo", "Renata Sales", "Samuel Prado", "Tatiane Moura",
]  # fmt: skip

TITULOS = [
    "Erro ao gerar etiqueta de expedição", "Relatório de horas extras por centro de custo",
    "Acesso ao módulo de cobrança para novo analista", "Integração Sankhya travando nota de entrada",
    "Tela de apontamento lenta na produção", "Regra de desconto por volume no comercial",
    "Impressora da qualidade sem driver", "Dashboard de OEE para manutenção",
    "Automatizar envio de boletos", "Ajuste no cálculo de comissão", "Cadastro duplicado de fornecedor",
    "Backup do servidor de arquivos", "Campo obrigatório de lote no recebimento",
    "Alerta de estoque mínimo por WhatsApp", "Exportar inventário em XLSX",
    "Permissão para aprovar solicitações", "Migração de planilha de RH", "VPN caindo no financeiro",
]  # fmt: skip


class Command(BaseCommand):
    help = "Popula o banco com dados de demonstração do protótipo"

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(42)
        self.setores()
        self.usuarios()
        self.categorias_e_sla()
        self.centros_custo()
        self.projetos()
        self.chamados()
        self.tipos_e_apontamentos()
        self.documentacao()
        self.almoxarifado()
        self.stdout.write(self.style.SUCCESS("Seed concluído. Login: admin / admin"))

    def setores(self):
        self.por_sigla = {}
        for nome, sigla in SETORES:
            s, _ = Setor.objects.get_or_create(sigla=sigla, defaults={"nome": nome})
            self.por_sigla[sigla] = s

    def usuarios(self):
        grupos = {g.name: g for g in Group.objects.all()}
        ti = self.por_sigla["TI"]
        admin, criado = User.objects.get_or_create(
            username="admin",
            defaults={"first_name": "Administrador", "email": "admin@lifelaboral.local",
                      "matricula": "0001", "setor": ti, "is_staff": True, "is_superuser": True},
        )  # fmt: skip
        if criado:
            admin.set_password("admin")
            admin.save()
        admin.groups.set([grupos[papeis.ADMINISTRADOR]])
        self.admin = admin

        siglas = [s for _, s in SETORES]
        self.usuarios_por_setor: dict[str, list[User]] = {s: [] for s in siglas}
        for i, nome in enumerate(NOMES):
            sigla = "TI" if i < 8 else siglas[i % (len(siglas) - 1)]
            primeiro, ultimo = nome.split(" ", 1)
            username = f"{primeiro.lower()}.{ultimo.split()[0].lower()}"
            u, criado = User.objects.get_or_create(
                username=username,
                defaults={"first_name": primeiro, "last_name": ultimo, "matricula": f"{400 + i:04d}",
                          "email": f"{username}@lifelaboral.local", "setor": self.por_sigla[sigla]},
            )  # fmt: skip
            if criado:
                u.set_password("senha123")
                u.save()
            self.usuarios_por_setor[sigla].append(u)

        # Papéis: 1º de TI = Gerente de TI; 1º de cada setor = Gerente; 2º = Responsável; demais Colaborador
        for sigla, lista in self.usuarios_por_setor.items():
            for idx, u in enumerate(lista):
                if sigla == "TI" and idx == 0:
                    papel = papeis.GERENTE_TI
                elif sigla == "CMP" and idx <= 1:
                    papel = papeis.COMPRAS
                elif idx == 0:
                    papel = papeis.GERENTE_SETOR
                elif idx == 1:
                    papel = papeis.RESPONSAVEL
                else:
                    papel = papeis.COLABORADOR
                u.groups.set([grupos[papel]])
                invalidar_papeis(u)
            if lista:
                setor = self.por_sigla[sigla]
                setor.responsavel = lista[min(1, len(lista) - 1)]
                setor.save(update_fields=["responsavel"])

    def categorias_e_sla(self):
        self.categorias = []
        for nome, slug, exige in CATEGORIAS:
            c, _ = Categoria.objects.get_or_create(slug=slug, defaults={"nome": nome, "exige_documentacao": exige})
            self.categorias.append(c)
            for prio, horas in {"critica": 4, "alta": 24, "media": 48, "baixa": 72}.items():
                RegraSLA.objects.get_or_create(categoria=c, prioridade=prio, defaults={"horas_uteis": horas})

    def centros_custo(self):
        for i, (nome, sigla) in enumerate(SETORES, start=1):
            CentroCusto.objects.get_or_create(
                codigo=f"{2000 + i:04d}", defaults={"descricao": f"Operação {nome}", "setor": self.por_sigla[sigla]}
            )

    def projetos(self):
        if Projeto.objects.exists():
            return
        fases = [f for f in Projeto.Fase if f not in ("concluido", "cancelado")]
        ti = self.usuarios_por_setor["TI"]
        siglas = [s for _, s in SETORES]
        hoje = timezone.localdate()
        for i in range(17):
            sigla = siglas[i % len(siglas)]
            Projeto.objects.create(
                nome=f"Projeto {i + 1:02d} — {sigla}",
                setor_solicitante=self.por_sigla[sigla],
                patrocinador=self.usuarios_por_setor[sigla][0] if self.usuarios_por_setor[sigla] else self.admin,
                responsavel=ti[i % len(ti)],
                fase=fases[i % len(fases)],
                horas_estimadas=random.choice([40, 80, 120, 200]),
                inicio_previsto=hoje - timedelta(days=random.randint(0, 60)),
                fim_previsto=hoje + timedelta(days=random.randint(15, 120)),
            )
        for i in range(23):
            fase = "concluido" if i % 5 else "cancelado"
            sigla = siglas[i % len(siglas)]
            Projeto.objects.create(
                nome=f"Projeto encerrado {i + 1:02d}",
                setor_solicitante=self.por_sigla[sigla],
                patrocinador=self.admin,
                fase=fase,
                encerrado_em=date.today() - timedelta(days=random.randint(10, 400)),
                situacao_final="Entregue em produção" if fase == "concluido" else "Cancelado a pedido do setor",
            )

    def chamados(self):
        if Chamado.objects.exists():
            return
        ti = self.usuarios_por_setor["TI"]
        siglas = [s for _, s in SETORES if s != "TI"]
        prioridades = ["critica", "alta", "media", "media", "baixa"]
        status_seq = ["novo", "triagem", "fila", "execucao", "testes", "aguarda"]
        for i in range(34):
            sigla = siglas[i % len(siglas)]
            solicitante = random.choice(self.usuarios_por_setor[sigla])
            c = chamados_services.abrir_chamado(
                solicitante=solicitante,
                titulo=TITULOS[i % len(TITULOS)],
                descricao="Descrição gerada pelo seed_demo para conferência visual do protótipo.",
                categoria=random.choice(self.categorias),
                prioridade=random.choice(prioridades),
                horas_previstas_min=random.choice([60, 120, 240, 480]),
            )
            alvo = status_seq[i % len(status_seq)]
            caminho = ["triagem", "fila", "execucao", "testes"]
            for passo in caminho:
                if alvo == "novo":
                    break
                chamados_services.transicionar(chamado=c, para=passo, usuario=ti[0])
                if passo == alvo:
                    break
            if alvo == "aguarda":
                chamados_services.transicionar(chamado=c, para="aguarda", usuario=ti[0])
            if alvo not in ("novo", "triagem"):
                chamados_services.atribuir(chamado=c, responsavel=ti[i % len(ti)], usuario=ti[0])

    def tipos_e_apontamentos(self):
        for ordem, (nome, slug, exige, contabiliza) in enumerate(TIPOS_INICIAIS):
            TipoTrabalho.objects.get_or_create(
                slug=slug,
                defaults={"nome": nome, "exige_causa": exige, "contabiliza_capacidade": contabiliza, "ordem": ordem},
            )
        for nome in MOTIVOS_INICIAIS:
            MotivoRetrabalho.objects.get_or_create(nome=nome)
        if Apontamento.objects.exists():
            return
        tipos = list(TipoTrabalho.objects.all())
        motivos = list(MotivoRetrabalho.objects.all())
        ti = self.usuarios_por_setor["TI"]
        chamados = list(Chamado.objects.filter(responsavel__isnull=False).select_related("responsavel"))
        hoje = timezone.localtime(timezone.now()).replace(hour=8, minute=0, second=0, microsecond=0)
        for dia_offset in range(1, 15):  # duas semanas úteis para trás
            dia = hoje - timedelta(days=dia_offset)
            if dia.weekday() >= 5:
                continue
            for u in ti:
                cursor = dia
                for _ in range(random.randint(2, 4)):
                    tipo = random.choices(tipos, weights=[3, 6, 2, 2, 2, 1, 1, 2])[0]
                    dur = random.choice([30, 60, 90, 120])
                    meus = [c for c in chamados if c.responsavel_id == u.id] or chamados
                    causa = {}
                    if tipo.exige_causa:
                        causa = {"motivo_retrabalho": random.choice(motivos),
                                 "detalhe_retrabalho": "Ajuste após requisito incompleto do solicitante"}
                    ap = ap_services.criar_apontamento(
                        usuario=u, tipo=tipo, inicio=cursor, fim=cursor + timedelta(minutes=dur),
                        chamado=random.choice(meus), lancamento_manual=False, **causa,
                    )
                    if ap.pendente_aprovacao:  # retroativo > 7 dias: aprovado pelo Gerente de TI
                        ap_services.aprovar_apontamento(apontamento=ap, aprovador=ti[0])
                    cursor += timedelta(minutes=dur + 15)

    def documentacao(self):
        from documentacao.models import VersaoDocumento
        from documentacao.services import criar_rascunho, publicar_secao

        if VersaoDocumento.objects.exists():
            return
        ti = self.usuarios_por_setor["TI"]
        textos = {
            "contexto": "O setor relatou o problema ao gerar o processo; o erro ocorre desde a última atualização.",
            "regra": "Regra acordada com o solicitante: o cálculo passa a considerar o centro de custo do setor.",
            "solucao": "Ajuste no serviço de cálculo e novo relatório de conferência.",
            "teste": "Testado em homologação com os três cenários enviados pelo setor.",
        }
        for i, c in enumerate(Chamado.objects.filter(categoria__exige_documentacao=True)):
            autor = c.responsavel or ti[0]
            n_publicadas = i % 5  # 0..4 seções publicadas → alguns travados, alguns entregáveis
            for j, (secao, texto) in enumerate(textos.items()):
                if j < n_publicadas:
                    publicar_secao(chamado=c, secao=secao, conteudo=texto, autor=autor)
                elif j == n_publicadas:
                    from documentacao.services import obter_documento

                    doc = obter_documento(chamado=c, secao=secao, criado_por=autor)
                    criar_rascunho(documento=doc, conteudo=texto + " (rascunho)", autor=autor)

    def almoxarifado(self):
        from decimal import Decimal

        from almoxarifado import services as alm
        from almoxarifado.models import Item

        if Item.objects.exists():
            return
        compras = self.usuarios_por_setor["CMP"][0]
        catalogo = [
            ("MRO-4471", "Rolamento 6205 ZZ", "UN", "MAN", 10, "18.90"),
            ("MRO-4472", "Correia A-42", "UN", "MAN", 6, "32.50"),
            ("MRO-4480", "Graxa lítio 1kg", "KG", "MAN", 5, "24.00"),
            ("MRO-4501", "Fusível 10A", "UN", "MAN", 20, "1.20"),
            ("EPI-0101", "Luva nitrílica M (par)", "PC", "PRD", 40, "3.10"),
            ("EPI-0102", "Óculos de proteção", "UN", "PRD", 15, "8.75"),
            ("EPI-0110", "Protetor auricular", "UN", "PRD", 30, "1.90"),
            ("EMB-2001", "Caixa papelão 40x30x30", "UN", "EXP", 200, "2.35"),
            ("EMB-2002", "Fita adesiva 48mm", "UN", "EXP", 30, "4.60"),
            ("EMB-2010", "Etiqueta térmica 100x150 (rolo)", "UN", "EXP", 12, "27.00"),
            ("LAB-3001", "Reagente pH 500ml", "UN", "QLD", 4, "56.00"),
            ("LAB-3002", "Pipeta descartável 5ml (cx)", "CX", "QLD", 3, "41.00"),
            ("ESC-9001", "Papel A4 (resma)", "UN", "RH", 10, "22.90"),
            ("ESC-9002", "Toner HP 85A", "UN", "TI", 2, "189.00"),
            ("TI-7001", "Cabo de rede Cat6 1,5m", "UN", "TI", 10, "9.80"),
            ("TI-7002", "Mouse USB", "UN", "TI", 5, "29.90"),
        ]
        itens = {}
        for codigo, desc, un, sigla, minimo, custo in catalogo:
            itens[codigo] = Item.objects.create(
                codigo=codigo, descricao=desc, unidade=un, setor_dono=self.por_sigla[sigla],
                estoque_minimo=Decimal(minimo), custo_unitario=Decimal(custo), criado_por=compras,
            )
        # Entrada inicial por NF em cada setor dono
        from datetime import date as _date
        por_setor: dict[str, list] = {}
        for codigo, desc, un, sigla, minimo, custo in catalogo:
            por_setor.setdefault(sigla, []).append((itens[codigo], minimo, custo))
        for n, (sigla, lista) in enumerate(por_setor.items(), start=1):
            alm.entrada_por_nota(
                numero=f"{1000 + n}", serie="1", fornecedor="Distribuidora Industrial Ltda", cnpj="12.345.678/0001-90",
                emissao=_date.today() - timedelta(days=20), setor=self.por_sigla[sigla], usuario=compras,
                valor_total=sum(Decimal(c) * (m * 3) for _, m, c in lista),
                itens=[{"item": it, "quantidade_pedida": m * 3, "quantidade_recebida": m * 3, "custo_unitario": Decimal(c)}
                       for it, m, c in lista],
            )
        # Consumo: solicitações aprovadas e atendidas (algumas parciais) + uma saída sem OS (consumo geral)
        cc_por_setor = {cc.setor.sigla: cc for cc in CentroCusto.objects.select_related("setor")}
        for sigla, lista in por_setor.items():
            gente = self.usuarios_por_setor.get(sigla) or [self.admin]
            gerente, resp = gente[0], gente[min(1, len(gente) - 1)]
            for k in range(3):
                it, minimo, _ = lista[k % len(lista)]
                sol = alm.criar_solicitacao(
                    solicitante=random.choice(gente), centro_custo=cc_por_setor[sigla],
                    itens=[{"item": it, "quantidade": Decimal(max(1, minimo // 2))}],
                    os_ref=f"OS-{random.randint(1000, 9999)}" if k != 1 else "", urgente=(k == 2),
                )
                if k == 2:
                    continue  # fica aberta para a fila de aprovação
                alm.aprovar_solicitacao(solicitacao=sol, usuario=gerente if papeis.GERENTE_SETOR in gerente.papeis() else compras)
                alm.atender_solicitacao(solicitacao=sol, usuario=resp if papeis.RESPONSAVEL in resp.papeis() else compras)
        # Transferência que fura o mínimo da origem (alerta amarelo do protótipo)
        alm.transferir(item=itens["MRO-4501"], setor_origem=self.por_sigla["MAN"], setor_destino=self.por_sigla["PRD"],
                       quantidade=Decimal(45), motivo="Parada de linha na produção", usuario=compras)
        # Inventário fechado com divergências na Expedição
        inv = alm.abrir_inventario(setor=self.por_sigla["EXP"], responsavel=compras)
        for c in inv.contagens.select_related("item"):
            desvio = {"EMB-2001": -7, "EMB-2002": 2}.get(c.item.codigo, 0)
            alm.registrar_contagem(inventario=inv, item=c.item, saldo_contado=c.saldo_sistema + desvio, usuario=compras)
        alm.fechar_inventario(inventario=inv, usuario=compras)
        # Cotação em andamento
        cot = alm.abrir_cotacao(item=itens["MRO-4472"], quantidade=Decimal(24), prazo_resposta=date.today() + timedelta(days=5), usuario=compras)
        alm.adicionar_proposta(cotacao=cot, fornecedor="Correias & Cia", valor_unitario=Decimal("31.20"), prazo_entrega_dias=7)
        alm.adicionar_proposta(cotacao=cot, fornecedor="Distribuidora Industrial Ltda", valor_unitario=Decimal("33.00"), prazo_entrega_dias=3)

    def almoxarifado(self):
        from decimal import Decimal

        from almoxarifado import services as almox
        from almoxarifado.models import Item, Movimento

        if Item.objects.exists():
            return
        compras = self.usuarios_por_setor["CMP"][0]
        catalogo = [
            ("MRO-4471", "Parafuso sextavado M8 x 40", "UN", "MAN", 200, "0.85"),
            ("MRO-4472", "Porca M8", "UN", "MAN", 200, "0.30"),
            ("MRO-0900", "Óleo lubrificante ISO 68 — 1L", "L", "MAN", 10, "32.00"),
            ("MRO-1210", "Rolamento 6205 2RS", "UN", "MAN", 6, "28.50"),
            ("MRO-3300", "Correia A-42", "UN", "MAN", 4, "45.00"),
            ("EPI-0012", "Luva nitrílica G", "PC", "PRD", 50, "4.20"),
            ("EPI-0020", "Óculos de proteção", "UN", "PRD", 20, "9.90"),
            ("EPI-0031", "Protetor auricular plug", "PC", "PRD", 100, "1.10"),
            ("EMB-0100", "Caixa de papelão 40x30x30", "UN", "EXP", 300, "2.75"),
            ("EMB-0110", "Fita adesiva 48mm", "UN", "EXP", 60, "6.40"),
            ("EMB-0120", "Filme stretch 500mm", "UN", "EXP", 12, "38.00"),
            ("LAB-0200", "Reagente padrão 500ml", "UN", "QLD", 3, "120.00"),
            ("LAB-0210", "Luva de látex P", "PC", "QLD", 40, "3.10"),
            ("ESC-0300", "Papel A4 resma", "UN", "FIN", 10, "24.90"),
            ("ESC-0310", "Toner impressora 85A", "UN", "TI", 2, "89.00"),
            ("TI-0400", "Cabo de rede Cat6 3m", "UN", "TI", 10, "14.50"),
            ("TI-0410", "Mouse USB", "UN", "TI", 5, "35.00"),
            ("TI-0420", "Teclado ABNT2", "UN", "TI", 5, "62.00"),
        ]
        itens = {}
        for codigo, desc, un, sigla, minimo, custo in catalogo:
            itens[codigo] = Item.objects.create(
                codigo=codigo, descricao=desc, unidade=un, setor_dono=self.por_sigla[sigla],
                estoque_minimo=minimo, custo_unitario=Decimal(custo), criado_por=compras,
            )
        for codigo, item in itens.items():
            saldo_inicial = item.estoque_minimo * random.choice([Decimal("0.5"), Decimal("1.5"), Decimal("3"), Decimal("4")])
            almox.registrar_movimento(item=item, setor=item.setor_dono, tipo="entrada",
                                      quantidade=saldo_inicial, usuario=compras, justificativa="Saldo inicial")
        # consumo dos últimos dias
        ccs = {cc.setor_id: cc for cc in CentroCusto.objects.all()}
        for item in itens.values():
            setor = item.setor_dono
            gente = self.usuarios_por_setor[setor.sigla]
            for _ in range(random.randint(1, 4)):
                qtd = max(Decimal("1"), (item.estoque_minimo * Decimal("0.1")).quantize(Decimal("1")))
                ref = random.choice([{"centro_custo": ccs[setor.id]}, {"os_ref": f"OS-{random.randint(100, 999)}"}])
                try:
                    almox.registrar_movimento(item=item, setor=setor, tipo="saida", quantidade=qtd,
                                              usuario=random.choice(gente), **ref)
                except almox.SaldoInsuficiente:
                    break
        # uma transferência e uma solicitação aberta
        almox.transferir(item=itens["EPI-0012"], setor_origem=self.por_sigla["PRD"], setor_destino=self.por_sigla["MAN"],
                         quantidade=10, motivo="Equipe de manutenção na linha 2", usuario=compras)
        almox.criar_solicitacao(
            solicitante=self.usuarios_por_setor["MAN"][2], centro_custo=ccs[self.por_sigla["MAN"].id], os_ref="OS-512",
            urgente=True, itens=[{"item": itens["MRO-1210"], "quantidade": 2}, {"item": itens["MRO-3300"], "quantidade": 1}],
        )
        assert Movimento.objects.exists()
