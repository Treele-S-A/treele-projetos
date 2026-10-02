"""O sininho: avisos da própria pessoa, contagem das não lidas e marcar como lida."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import usuario_atual
from ..models import Notificacao, Usuario
from ..schemas import NotificacaoContagem, NotificacaoOut

router = APIRouter(prefix="/notificacoes", tags=["notificações"])


def _saida(n: Notificacao) -> NotificacaoOut:
    return NotificacaoOut(
        id=n.id,
        tipo=n.tipo,
        titulo=n.titulo,
        texto=n.texto,
        criada_em=n.criada_em,
        lida=n.lida_em is not None,
        documento_id=n.documento_id,
        obra_codigo=n.obra.codigo,
    )


@router.get("", response_model=list[NotificacaoOut])
def listar(
    limite: int = Query(50, ge=1, le=200),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    linhas = db.scalars(
        select(Notificacao)
        .where(Notificacao.usuario_id == usuario.id)
        .order_by(Notificacao.criada_em.desc(), Notificacao.id.desc())
        .limit(limite)
    )
    return [_saida(n) for n in linhas]


@router.get("/contagem", response_model=NotificacaoContagem)
def contagem(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    total = db.scalar(
        select(func.count())
        .select_from(Notificacao)
        .where(Notificacao.usuario_id == usuario.id, Notificacao.lida_em.is_(None))
    )
    return NotificacaoContagem(nao_lidas=total or 0)


@router.post("/{notificacao_id}/lida", status_code=status.HTTP_204_NO_CONTENT)
def marcar_lida(
    notificacao_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    n = db.get(Notificacao, notificacao_id)
    # Aviso de outra pessoa responde como inexistente: nem confirma que existe.
    if n is None or n.usuario_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificação não encontrada.")
    if n.lida_em is None:
        n.lida_em = datetime.now(timezone.utc)
        db.commit()


@router.post("/lidas", status_code=status.HTTP_204_NO_CONTENT)
def marcar_todas(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    db.execute(
        update(Notificacao)
        .where(Notificacao.usuario_id == usuario.id, Notificacao.lida_em.is_(None))
        .values(lida_em=datetime.now(timezone.utc))
    )
    db.commit()
