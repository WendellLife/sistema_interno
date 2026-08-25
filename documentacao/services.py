"""Documentação: seções por chamado/projeto, versões append-only, rascunho → publicação."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.auditoria import registrar

from .exceptions import ConteudoVazio, DestinoInvalido, VersaoJaPublicada
from .models import SECOES_OBRIGATORIAS, Documento, VersaoDocumento


def _validar_destino(chamado, projeto) -> None:
    if bool(chamado) == bool(projeto):
        raise DestinoInvalido()


@transaction.atomic
def criar_secoes(*, chamado=None, projeto=None, criado_por=None) -> list[Documento]:
    """Uma linha por seção (as 6). `obrigatorio` reflete a categoria do chamado."""
    _validar_destino(chamado, projeto)
    exige = bool(chamado and chamado.categoria.exige_documentacao)
    docs = []
    for secao in Documento.Secao:
        doc, _ = Documento.objects.get_or_create(
            chamado=chamado,
            projeto=projeto,
            secao=secao,
            defaults={"obrigatorio": exige and secao in SECOES_OBRIGATORIAS, "criado_por": criado_por},
        )
        docs.append(doc)
    return docs


def obter_documento(*, chamado=None, projeto=None, secao: str, criado_por=None) -> Documento:
    _validar_destino(chamado, projeto)
    exige = bool(chamado and chamado.categoria.exige_documentacao)
    doc, _ = Documento.objects.get_or_create(
        chamado=chamado,
        projeto=projeto,
        secao=secao,
        defaults={"obrigatorio": exige and secao in SECOES_OBRIGATORIAS, "criado_por": criado_por},
    )
    return doc


@transaction.atomic
def criar_rascunho(*, documento: Documento, conteudo: str, autor) -> VersaoDocumento:
    """Nova versão não publicada. Nunca altera versões existentes."""
    if not conteudo or not conteudo.strip():
        raise ConteudoVazio()
    documento = Documento.objects.select_for_update().get(pk=documento.pk)
    ultimo = documento.versoes.aggregate(m=Max("numero"))["m"] or 0
    versao = VersaoDocumento.objects.create(
        documento=documento, numero=ultimo + 1, conteudo=conteudo, autor=autor, criado_por=autor
    )
    registrar(
        usuario=autor,
        acao="documento.rascunho",
        objeto=documento,
        antes={"ultima_versao": ultimo or None},
        depois={"ultima_versao": versao.numero, "secao": documento.secao},
    )
    return versao


@transaction.atomic
def publicar_versao(*, versao: VersaoDocumento, usuario) -> VersaoDocumento:
    """Marca a versão como publicada e a torna `versao_atual` do documento."""
    versao = VersaoDocumento.objects.select_for_update().select_related("documento").get(pk=versao.pk)
    if versao.publicada_em:
        raise VersaoJaPublicada(versao.numero)
    doc = versao.documento
    anterior = doc.versao_atual.numero if doc.versao_atual_id else None
    versao.publicada_em = timezone.now()
    versao.save(update_fields=["publicada_em", "atualizado_em"])
    doc.versao_atual = versao
    doc.save(update_fields=["versao_atual", "atualizado_em"])
    registrar(
        usuario=usuario,
        acao="documento.publicar",
        objeto=doc,
        antes={"versao_atual": anterior},
        depois={"versao_atual": versao.numero, "secao": doc.secao},
    )
    return versao


def publicar_secao(*, chamado=None, projeto=None, secao: str, conteudo: str, autor) -> VersaoDocumento:
    """Atalho: rascunho + publicação em uma chamada (usado por testes e seed)."""
    doc = obter_documento(chamado=chamado, projeto=projeto, secao=secao, criado_por=autor)
    versao = criar_rascunho(documento=doc, conteudo=conteudo, autor=autor)
    return publicar_versao(versao=versao, usuario=autor)
