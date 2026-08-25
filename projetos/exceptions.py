from rest_framework import status

from core.exceptions import RegraDeNegocio


class FaseInvalida(RegraDeNegocio):
    codigo = "fase_invalida"

    def __init__(self, de: str, para: str):
        super().__init__(f"Não é possível mover de '{de}' para '{para}'.", de=de, para=para)


class EncerramentoSemData(RegraDeNegocio):
    codigo = "encerramento_sem_data"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self):
        super().__init__("Concluir ou cancelar exige data de encerramento e situação final.")


class ProjetoEncerrado(RegraDeNegocio):
    codigo = "projeto_encerrado"

    def __init__(self):
        super().__init__("Projeto concluído ou cancelado não pode ser alterado.")


class AlocacaoExcedida(RegraDeNegocio):
    codigo = "alocacao_excedida"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self, usuario, total: int):
        super().__init__(f"{usuario.nome} ficaria com {total}% alocado.", total=total)
