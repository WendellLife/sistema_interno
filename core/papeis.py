"""Papéis do sistema. São `Group` do Django com estes nomes exatos."""

COLABORADOR = "Colaborador"
RESPONSAVEL = "Responsavel"
GERENTE_SETOR = "GerenteSetor"
GERENTE_TI = "GerenteTI"
COMPRAS = "Compras"
ADMINISTRADOR = "Administrador"

TODOS = [COLABORADOR, RESPONSAVEL, GERENTE_SETOR, GERENTE_TI, COMPRAS, ADMINISTRADOR]

# Papéis que enxergam todos os setores nas listagens
VE_TODOS_SETORES = {GERENTE_TI, COMPRAS, ADMINISTRADOR}
# Papéis que aprovam horas
APROVA_HORAS = {GERENTE_SETOR, GERENTE_TI, ADMINISTRADOR}

# Módulos (chave usada na matriz de permissões e no menu)
MODULOS = ["painel", "tarefas", "tarefa", "documentacao", "almoxarifado", "compras", "projetos", "config"]

# Matriz padrão (04-API-E-PERMISSOES.md §9). "E" editar, "V" ver, "-" sem acesso.
MATRIZ_PADRAO: dict[str, dict[str, str]] = {
    "painel":       {COLABORADOR: "-", RESPONSAVEL: "V", GERENTE_SETOR: "V", GERENTE_TI: "E", COMPRAS: "V", ADMINISTRADOR: "E"},
    "tarefas":      {COLABORADOR: "E", RESPONSAVEL: "E", GERENTE_SETOR: "V", GERENTE_TI: "E", COMPRAS: "V", ADMINISTRADOR: "E"},
    "tarefa":       {COLABORADOR: "E", RESPONSAVEL: "V", GERENTE_SETOR: "V", GERENTE_TI: "E", COMPRAS: "-", ADMINISTRADOR: "E"},
    "documentacao": {COLABORADOR: "E", RESPONSAVEL: "E", GERENTE_SETOR: "V", GERENTE_TI: "E", COMPRAS: "-", ADMINISTRADOR: "E"},
    # Colaborador tem "E" porque SOLICITA. Dar baixa no estoque é outra coisa e depende do
    # papel: ver `almoxarifado.permissions.MOVIMENTA` (Responsável, Compras, Administrador).
    "almoxarifado": {COLABORADOR: "E", RESPONSAVEL: "E", GERENTE_SETOR: "V", GERENTE_TI: "V", COMPRAS: "E", ADMINISTRADOR: "E"},
    "compras":      {COLABORADOR: "-", RESPONSAVEL: "-", GERENTE_SETOR: "V", GERENTE_TI: "V", COMPRAS: "E", ADMINISTRADOR: "E"},
    "projetos":     {COLABORADOR: "-", RESPONSAVEL: "V", GERENTE_SETOR: "V", GERENTE_TI: "E", COMPRAS: "V", ADMINISTRADOR: "E"},
    "config":       {COLABORADOR: "-", RESPONSAVEL: "-", GERENTE_SETOR: "-", GERENTE_TI: "-", COMPRAS: "-", ADMINISTRADOR: "E"},
}  # fmt: skip
