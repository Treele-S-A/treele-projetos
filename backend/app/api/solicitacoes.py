"""Solicitação de revisão — pedido, autorização, anexos e abertura dos anexos.

Os anexos seguem o fluxo dos arquivos de projeto: a API cria a linha e
devolve uma URL assinada, o navegador sobe direto para o armazenamento, e a
API confere que chegou. Foto de celular passa fácil do limite de corpo de
requisição da hospedagem; por isso nada de passar bytes pela API.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ContextoObra, montar_contexto, status_visiveis, usuario_atual
from ..enums import StatusArquivo, StatusRevisao, StatusSolicitacao
from ..models import AnexoSolicitacao, Documento, SolicitacaoRevisao, Usuario
from ..schemas import (
    AnexoIniciar,
    AnexoIniciarSaida,
    AnexoOut,
    SolicitacaoCriar,
    SolicitacaoOut,
    SolicitacaoRecusar,
)
from ..services import auditoria
from ..services import notificacoes
from ..services import solicitacoes as servico
from ..services.storage import armazenamento, chave_anexo
from ..services.titulos import limpar_descricao

router = APIRouter(tags=["solicitações"])


def _documento(db: Session, usuario: Usuario, documento_id: int) -> tuple[Documento, ContextoObra]:
    """Documento que a pessoa enxerga — com a mesma regra da tela do documento —
    e que é assunto da equipe: o perfil comercial não vê pedidos."""
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    ctx = montar_contexto(db, usuario, documento.obra_id)
    visiveis = status_visiveis(ctx)
    if not ctx.ve_disciplina(documento.disciplina.codigo) or not any(
        r.status in visiveis for r in documento.revisoes
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    ctx.somente_equipe()
    return documento, ctx


def _minha_solicitacao(db: Session, usuario: Usuario, solicitacao_id: int) -> SolicitacaoRevisao:
    """Anexo só entra pela mão de quem fez o pedido, e com o pedido valendo
    (aberto ou autorizado — o do coordenador já nasce autorizado)."""
    solicitacao = db.get(SolicitacaoRevisao, solicitacao_id)
    if solicitacao is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Solicitação não encontrada.")
    _documento(db, usuario, solicitacao.documento_id)
    if solicitacao.criada_por_id != usuario.id and not usuario.admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Só quem fez a solicitação anexa arquivos a ela."
        )
    if solicitacao.status not in servico.ACEITA_ANEXO:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Esta solicitação já foi {solicitacao.status.value} e não aceita anexos.",
        )
    return solicitacao


def _decidir(
    db: Session, usuario: Usuario, solicitacao_id: int
) -> tuple[SolicitacaoRevisao, ContextoObra]:
    """Pedido aberto, nas mãos de quem pode autorizar."""
    solicitacao = db.get(SolicitacaoRevisao, solicitacao_id)
    if solicitacao is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Solicitação não encontrada.")
    _, ctx = _documento(db, usuario, solicitacao.documento_id)
    ctx.exigir(
        "autorizar_revisao", "Somente o coordenador da obra autoriza ou recusa revisões."
    )
    if solicitacao.status != StatusSolicitacao.aberta:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Esta solicitação já foi {solicitacao.status.value}. Recarregue a página.",
        )
    return solicitacao, ctx


@router.post(
    "/documentos/{documento_id}/solicitacoes",
    response_model=SolicitacaoOut,
    status_code=status.HTTP_201_CREATED,
)
def solicitar(
    documento_id: int,
    dados: SolicitacaoCriar,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Pedido da obra nasce aberto, à espera do coordenador. O do coordenador
    já nasce autorizado: é a revisão que vem do escritório (05/10/2026)."""
    documento, ctx = _documento(db, usuario, documento_id)
    ctx.exigir(
        "solicitar_revisao", "Somente o coordenador ou a obra pedem revisão de projeto."
    )
    autoriza = ctx.pode("autorizar_revisao")

    liberada = next(
        (r for r in documento.revisoes if r.status == StatusRevisao.liberado_para_obra), None
    )
    if liberada is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Só se pede revisão de projeto liberado para obra — este documento ainda "
            "não tem revisão liberada.",
        )

    descricao = limpar_descricao(dados.descricao)
    problema = servico.problema_no_pedido(descricao)
    if problema:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problema)

    solicitacao = SolicitacaoRevisao(
        documento_id=documento.id,
        revisao_id=liberada.id,
        descricao=descricao,
        criada_por_id=usuario.id,
    )
    if autoriza:
        solicitacao.status = StatusSolicitacao.autorizada
        solicitacao.decidida_em = datetime.now(timezone.utc)
        solicitacao.decidida_por_id = usuario.id
    db.add(solicitacao)
    db.flush()
    auditoria.registrar(
        db, acao="revisao_autorizada" if autoriza else "revisao_solicitada",
        entidade="solicitacao", entidade_id=solicitacao.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={"documento": documento.codigo, "revisao": liberada.numero, "sem_pedido": autoriza},
        request=request,
    )
    avisos = (
        notificacoes.ao_autorizar(db, solicitacao, usuario)
        if autoriza
        else notificacoes.ao_solicitar(db, solicitacao, usuario)
    )
    db.commit()
    notificacoes.enviar_emails(db, avisos)
    db.refresh(solicitacao)
    return servico.saida(solicitacao)


@router.post("/solicitacoes/{solicitacao_id}/autorizar", response_model=SolicitacaoOut)
def autorizar(
    solicitacao_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """O coordenador autoriza o pedido da obra: o documento passa a aceitar
    revisão nova, e o projetista da última revisão é avisado."""
    solicitacao, ctx = _decidir(db, usuario, solicitacao_id)
    solicitacao.status = StatusSolicitacao.autorizada
    solicitacao.decidida_em = datetime.now(timezone.utc)
    solicitacao.decidida_por_id = usuario.id
    auditoria.registrar(
        db, acao="revisao_autorizada", entidade="solicitacao", entidade_id=solicitacao.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={"documento": solicitacao.documento.codigo, "sem_pedido": False},
        request=request,
    )
    db.flush()
    avisos = notificacoes.ao_autorizar(db, solicitacao, usuario)
    db.commit()
    notificacoes.enviar_emails(db, avisos)
    db.refresh(solicitacao)
    return servico.saida(solicitacao)


@router.post("/solicitacoes/{solicitacao_id}/recusar", response_model=SolicitacaoOut)
def recusar(
    solicitacao_id: int,
    dados: SolicitacaoRecusar,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """O coordenador recusa o pedido, dizendo por quê. Quem pediu é avisado."""
    solicitacao, ctx = _decidir(db, usuario, solicitacao_id)
    motivo = limpar_descricao(dados.motivo)
    problema = servico.problema_no_motivo(motivo)
    if problema:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problema)
    solicitacao.status = StatusSolicitacao.recusada
    solicitacao.decidida_em = datetime.now(timezone.utc)
    solicitacao.decidida_por_id = usuario.id
    solicitacao.motivo_recusa = motivo
    auditoria.registrar(
        db, acao="revisao_recusada", entidade="solicitacao", entidade_id=solicitacao.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={"documento": solicitacao.documento.codigo},
        request=request,
    )
    db.flush()
    avisos = notificacoes.ao_recusar(db, solicitacao, usuario)
    db.commit()
    notificacoes.enviar_emails(db, avisos)
    db.refresh(solicitacao)
    return servico.saida(solicitacao)


@router.post(
    "/solicitacoes/{solicitacao_id}/anexos",
    response_model=AnexoIniciarSaida,
    status_code=status.HTTP_201_CREATED,
)
def iniciar_anexo(
    solicitacao_id: int,
    dados: AnexoIniciar,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    solicitacao = _minha_solicitacao(db, usuario, solicitacao_id)

    tipo = servico.tipo_do_anexo(dados.nome_arquivo)
    if tipo is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Anexe fotos (JPG, PNG ou WebP) ou PDF.",
        )
    if dados.tamanho > servico.ANEXO_MAX_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Cada anexo pode ter até {servico.ANEXO_MAX_MB} MB.",
        )
    if len(solicitacao.anexos) >= servico.ANEXO_MAX_POR_SOLICITACAO:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Uma solicitação aceita até {servico.ANEXO_MAX_POR_SOLICITACAO} anexos.",
        )

    documento = solicitacao.documento
    chave = chave_anexo(
        documento.obra.codigo, documento.codigo, solicitacao.id, dados.nome_arquivo
    )
    anexo = AnexoSolicitacao(
        solicitacao_id=solicitacao.id,
        nome_original=dados.nome_arquivo,
        storage_key=chave,
        content_type=tipo,
        tamanho=0,
    )
    db.add(anexo)
    db.flush()
    destino = armazenamento.destino_upload(chave, tipo)
    db.commit()
    return AnexoIniciarSaida(
        anexo_id=anexo.id, url=destino.url, metodo=destino.metodo, headers=destino.headers
    )


@router.post("/anexos/{anexo_id}/confirmar", response_model=AnexoOut)
def confirmar_anexo(
    anexo_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    anexo = db.get(AnexoSolicitacao, anexo_id)
    if anexo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo não encontrado.")
    _minha_solicitacao(db, usuario, anexo.solicitacao_id)

    existe, tamanho = armazenamento.info(anexo.storage_key)
    if not existe:
        anexo.status = StatusArquivo.erro
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "O anexo não chegou ao armazenamento. Tente de novo."
        )
    # O tamanho declarado no início é do remetente; este é o que chegou.
    if tamanho > servico.ANEXO_MAX_MB * 1024 * 1024:
        armazenamento.remover(anexo.storage_key)
        db.delete(anexo)
        db.commit()
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Cada anexo pode ter até {servico.ANEXO_MAX_MB} MB.",
        )

    anexo.status = StatusArquivo.disponivel
    anexo.tamanho = tamanho
    db.commit()
    return anexo


@router.get("/anexos/{anexo_id}/visualizar")
def visualizar_anexo(
    anexo_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """URL assinada que abre a foto ou o PDF no navegador."""
    anexo = db.get(AnexoSolicitacao, anexo_id)
    if anexo is None or anexo.status != StatusArquivo.disponivel:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo não encontrado.")
    _documento(db, usuario, anexo.solicitacao.documento_id)
    return {
        "url": armazenamento.url_anexo(anexo.storage_key, anexo.nome_original, anexo.content_type)
    }
