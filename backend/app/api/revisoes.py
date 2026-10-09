from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import montar_contexto, status_visiveis, usuario_atual
from ..models import Revisao, Usuario
from ..enums import StatusRevisao
from ..schemas import PublicarEntrada, ReprovarEntrada, RevisaoAtualizar, RevisaoOut
from ..services import auditoria
from ..services import revisoes as servico
from ..services import notificacoes
from ..services import solicitacoes as servico_solicitacoes

router = APIRouter(prefix="/revisoes", tags=["revisões"])


def _carregar(db: Session, usuario: Usuario, revisao_id: int):
    revisao = db.get(Revisao, revisao_id)
    if revisao is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revisão não encontrada.")
    ctx = montar_contexto(db, usuario, revisao.documento.obra_id)
    # A mesma regra das listas: o que a pessoa não vê, não existe para ela —
    # nem pelo número da revisão no endereço.
    if revisao.status not in status_visiveis(ctx) or not ctx.ve_disciplina(
        revisao.documento.disciplina.codigo
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revisão não encontrada.")
    return revisao, ctx


@router.get("/{revisao_id}", response_model=RevisaoOut)
def detalhe(
    revisao_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    revisao, _ = _carregar(db, usuario, revisao_id)
    return revisao


@router.get("/{revisao_id}/verificar")
def verificar(
    revisao_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """O que ainda impede esta revisão de ser liberada.

    A interface consulta isto para explicar o botão desabilitado em vez de só
    recusar a ação depois do clique.
    """
    revisao, ctx = _carregar(db, usuario, revisao_id)
    impedimentos = servico.conferir_publicacao(
        db, revisao, ctx.obra.regra_companheiro
    )
    return {
        "pode_publicar": ctx.pode("publicar") and not impedimentos,
        "tem_permissao": ctx.pode("publicar"),
        "impedimentos": impedimentos,
        "tipos_presentes": sorted(servico.tipos_disponiveis(revisao)),
        "regra_companheiro": ctx.obra.regra_companheiro,
    }


@router.patch("/{revisao_id}", response_model=RevisaoOut)
def atualizar(
    revisao_id: int,
    dados: RevisaoAtualizar,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    revisao, ctx = _carregar(db, usuario, revisao_id)
    ctx.exigir("enviar")

    if dados.descricao is not None:
        revisao.descricao = dados.descricao.strip() or None

    auditoria.registrar(
        db, acao="revisao_atualizada", entidade="revisao", entidade_id=revisao.id,
        usuario=usuario, obra_id=ctx.obra.id, request=request,
    )
    db.commit()
    return revisao


@router.post("/{revisao_id}/publicar", response_model=RevisaoOut)
def publicar(
    revisao_id: int,
    dados: PublicarEntrada,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Libera para obra — o lado "aprovado" da análise crítica. Torna
    obsoletas as revisões anteriores liberadas."""
    revisao, ctx = _carregar(db, usuario, revisao_id)
    ctx.exigir("publicar", "Somente o coordenador da obra pode liberar revisões.")

    impedimentos = servico.conferir_publicacao(
        db, revisao, ctx.obra.regra_companheiro
    )
    if impedimentos:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "mensagem": "Esta revisão ainda não pode ser liberada para obra.",
                "erros": impedimentos,
            },
        )

    # Pedidos de revisão que esta revisão atende, marcados por quem libera.
    # Conferidos antes de liberar: um pedido inválido não libera nada.
    atendidos = servico_solicitacoes.pedidos_marcados(db, revisao, dados.solicitacoes_atendidas)
    if atendidos is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Alguma das solicitações marcadas não está aberta neste documento. "
            "Recarregue a página e marque de novo.",
        )

    if dados.descricao:
        revisao.descricao = dados.descricao.strip()

    obsoletas = servico.publicar(db, revisao, usuario.id, dados.observacao)
    servico_solicitacoes.atender(db, revisao, atendidos)

    auditoria.registrar(
        db, acao="revisao_publicada", entidade="revisao", entidade_id=revisao.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={
            "documento": revisao.documento.codigo,
            "revisao": revisao.numero,
            "obsoletadas": [r.numero for r in obsoletas],
            "solicitacoes_atendidas": [s.id for s in atendidos],
            "observacao": revisao.observacao,
        },
        request=request,
    )
    avisos = notificacoes.ao_liberar(db, revisao, usuario, obsoletas)
    db.commit()
    notificacoes.enviar_emails(db, avisos)
    db.refresh(revisao)
    return revisao


@router.post("/{revisao_id}/reprovar", response_model=RevisaoOut)
def reprovar(
    revisao_id: int,
    dados: ReprovarEntrada,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Reprova na análise crítica (TREELE, 09/10/2026). A observação é
    obrigatória e vai para quem enviou a revisão, no sistema e por e-mail. A
    correção vem numa revisão nova, que não precisa de outra autorização."""
    revisao, ctx = _carregar(db, usuario, revisao_id)
    ctx.exigir("publicar", "Somente o coordenador da obra pode reprovar revisões.")
    if revisao.status != StatusRevisao.em_revisao:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A R{revisao.numero} está {revisao.status.rotulo.lower()}: só revisão "
            "em revisão passa pela análise crítica.",
        )
    observacao = dados.observacao.strip()
    if not observacao:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Escreva a observação: é o que o projetista precisa corrigir.",
        )

    servico.reprovar(db, revisao, usuario.id, observacao)
    auditoria.registrar(
        db, acao="revisao_reprovada", entidade="revisao", entidade_id=revisao.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={
            "documento": revisao.documento.codigo,
            "revisao": revisao.numero,
            "observacao": observacao,
        },
        request=request,
    )
    avisos = notificacoes.ao_reprovar(db, revisao, usuario)
    db.commit()
    notificacoes.enviar_emails(db, avisos)
    db.refresh(revisao)
    return revisao


@router.post("/{revisao_id}/cancelar", response_model=RevisaoOut)
def cancelar(
    revisao_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Cancela a revisão: ela fica no histórico, dizendo que não vale.

    Revisões não se excluem (TREELE, 09/10/2026). O coordenador cancela a que
    está em revisão; o administrador, em qualquer status, a qualquer tempo —
    inclusive a liberada, e aí a liberada anterior volta a valer.
    """
    revisao, ctx = _carregar(db, usuario, revisao_id)
    ctx.exigir("cancelar", "Somente o coordenador da obra pode cancelar revisões.")

    if revisao.status == StatusRevisao.cancelado:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta revisão já está cancelada.")
    if revisao.status != StatusRevisao.em_revisao and not usuario.admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"A R{revisao.numero} está {revisao.status.rotulo.lower()}. Só um "
            "administrador cancela revisão fora da análise.",
        )

    situacao = revisao.status.value
    restaurada = servico.cancelar(db, revisao)
    auditoria.registrar(
        db, acao="revisao_cancelada", entidade="revisao", entidade_id=revisao.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={
            "documento": revisao.documento.codigo,
            "revisao": revisao.numero,
            "situacao_revisao": situacao,
            "restaurada": restaurada.numero if restaurada else None,
        },
        request=request,
    )
    db.commit()
    db.refresh(revisao)
    return revisao
