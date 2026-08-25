from rest_framework import status

from core.exceptions import RegraDeNegocio


class VersaoJaPublicada(RegraDeNegocio):
    codigo = "versao_ja_publicada"

    def __init__(self, numero: int):
        super().__init__(f"A versão {numero} já está publicada.", numero=numero)


class ConteudoVazio(RegraDeNegocio):
    codigo = "conteudo_vazio"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self):
        super().__init__("O conteúdo da seção não pode ficar vazio.")


class DestinoInvalido(RegraDeNegocio):
    codigo = "destino_invalido"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self):
        super().__init__("Informe exatamente um destino: chamado ou projeto.")
