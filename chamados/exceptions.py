from rest_framework import status

from core.exceptions import RegraDeNegocio


class TransicaoInvalida(RegraDeNegocio):
    codigo = "transicao_invalida"

    def __init__(self, de: str, para: str):
        super().__init__(
            f"Não é possível ir de '{de}' para '{para}'.", de=de, para=para
        )


class DocumentacaoIncompleta(RegraDeNegocio):
    codigo = "documentacao_incompleta"

    def __init__(self, faltando: list[str]):
        super().__init__(
            "Publique as seções obrigatórias antes de entregar.", faltando=faltando
        )


class JustificativaObrigatoria(RegraDeNegocio):
    codigo = "justificativa_obrigatoria"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self):
        super().__init__("Cancelamento exige justificativa.")


class SemPermissaoParaAcao(RegraDeNegocio):
    codigo = "sem_permissao"
    status_http = status.HTTP_403_FORBIDDEN
