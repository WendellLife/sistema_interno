from rest_framework import status

from core.exceptions import RegraDeNegocio, ValidacaoDeCampo


class CausaObrigatoria(ValidacaoDeCampo):
    def __init__(self, campo="motivo_retrabalho", mensagem="Obrigatório para retrabalho."):
        super().__init__(campo, mensagem)


class ConflitoDeHoras(RegraDeNegocio):
    codigo = "conflito_horas"
    status_http = status.HTTP_400_BAD_REQUEST

    def __init__(self, conflitante):
        from django.utils import timezone

        ini = timezone.localtime(conflitante.inicio)
        fim = timezone.localtime(conflitante.fim) if conflitante.fim else None
        faixa = f"{ini:%H:%M}–{fim:%H:%M}" if fim else f"{ini:%H:%M}–em andamento"
        super().__init__(
            f"Conflita com apontamento de {conflitante.tipo.nome} ({faixa})",
            conflitante_id=conflitante.pk,
        )


class SemCronometroAberto(RegraDeNegocio):
    codigo = "sem_cronometro"
    status_http = status.HTTP_404_NOT_FOUND

    def __init__(self):
        super().__init__("Nenhum cronômetro em andamento.")


class ApontamentoNaoPendente(RegraDeNegocio):
    codigo = "nao_pendente"

    def __init__(self):
        super().__init__("Este apontamento não está aguardando aprovação.")


class ForaDoEscopoDeAprovacao(RegraDeNegocio):
    codigo = "fora_do_escopo"
    status_http = status.HTTP_403_FORBIDDEN

    def __init__(self):
        super().__init__("Você só pode aprovar horas do seu setor.")
