from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import montar_contexto, status_visiveis, usuario_atual
from ..models import Revisao, Usuario
from ..schemas import ExclusaoRevisaoSaida, PublicarEntrada, RevisaoAtualizar, RevisaoOut
from ..services import auditoria
from ..services import revisoes as servico

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
    """Libera para obra. Torna obsoletas as revisões anteriores liberadas."""
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

    if dados.descricao:
        revisao.descricao = dados.descricao.strip()

    obsoletas = servico.publicar(db, revisao, usuario.id)

    auditoria.registrar(
        db, acao="revisao_publicada", entidade="revisao", entidade_id=revisao.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={
            "documento": revisao.documento.codigo,
            "revisao": revisao.numero,
            "obsoletadas": [r.numero for r in obsoletas],
        },
        request=request,
    )
    db.commit()
    db.refresh(revisao)
    return revisao


@router.delete("/{revisao_id}", response_model=ExclusaoRevisaoSaida)
def excluir(
    revisao_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Exclui a revisão e os arquivos dela, em qualquer status. Só administrador.

    Diferente de cancelar: cancelada, a revisão continua no histórico dizendo
    que não vale. Excluída, ela some — é para o que nunca deveria ter entrado
    (obra errada, arquivo trocado). O registro de atividades guarda o que saiu.
    """
    revisao, ctx = _carregar(db, usuario, revisao_id)
    if not usuario.admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Somente um administrador pode excluir revisões."
        )

    codigo = revisao.documento.codigo
    numero = revisao.numero
    situacao = revisao.status.value

    resultado = servico.excluir_revisao(db, revisao)
    auditoria.registrar(
        db, acao="revisao_excluida", entidade="revisao", entidade_id=revisao_id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={
            "documento": codigo,
            "revisao": numero,
            "situacao_revisao": situacao,
            "arquivos": resultado.arquivos,
            "restaurada": resultado.restaurada.numero if resultado.restaurada else None,
            "documento_excluido": resultado.documento_excluido,
        },
        request=request,
    )
    db.commit()
    servico.remover_do_armazenamento(db, resultado.chaves)

    return ExclusaoRevisaoSaida(
        restaurada=resultado.restaurada.numero if resultado.restaurada else None,
        documento_excluido=resultado.documento_excluido,
    )


@router.post("/{revisao_id}/cancelar", response_model=RevisaoOut)
def cancelar(
    revisao_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    revisao, ctx = _carregar(db, usuario, revisao_id)
    ctx.exigir("cancelar", "Somente o coordenador da obra pode cancelar revisões.")

    if revisao.status.value == "liberado_para_obra":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Não é possível cancelar uma revisão liberada para obra. "
            "Publique uma revisão nova que a substitua.",
        )

    servico.cancelar(db, revisao)
    auditoria.registrar(
        db, acao="revisao_cancelada", entidade="revisao", entidade_id=revisao.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={"documento": revisao.documento.codigo, "revisao": revisao.numero},
        request=request,
    )
    db.commit()
    db.refresh(revisao)
    return revisao
