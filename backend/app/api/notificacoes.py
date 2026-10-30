"""O sininho: avisos da própria pessoa, contagem das não lidas e marcar como lida."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import usuario_atual
from ..models import Notificacao, Usuario
from ..schemas import EmailTesteSaida, NotificacaoContagem, NotificacaoOut
from ..services import email, email_modelo

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
        obra_codigo=n.obra.codigo if n.obra else None,
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


@router.post("/email-teste", response_model=EmailTesteSaida)
def email_teste(usuario: Usuario = Depends(usuario_atual)):
    """Manda um e-mail para o próprio administrador, para conferir a configuração
    sem gerar aviso falso para a equipe. Só administrador."""
    if not usuario.admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Somente um administrador testa o envio de e-mail."
        )
    saudacao = f"Olá, {usuario.nome.split()[0]}."
    corpo = (
        "Se este e-mail chegou, as notificações por e-mail estão funcionando.\n\n"
        "Como vão chegar os avisos:\nRevisão enviada, solicitada, autorizada, recusada e "
        "liberada para obra — cada um para quem precisa saber."
    )
    erro = email.diagnosticar(
        email.Mensagem(
            para=usuario.email,
            assunto="Teste de e-mail · Treèle Projetos",
            texto=(
                f"{saudacao}\n\n{corpo}\n\n"
                f"{settings.endereco_site}\n\n—\nTreèle Projetos · aviso automático."
            ),
            html=email_modelo.html(
                tipo="teste",
                saudacao=saudacao,
                titulo="As notificações por e-mail estão funcionando",
                texto=corpo,
                obra="Treèle Projetos",
                cor_obra=None,
                link=settings.endereco_site,
                rotulo_botao="Abrir o sistema",
                cid_simbolo=email.CID_SIMBOLO,
            ),
        )
    )
    return EmailTesteSaida(
        enviado=erro is None, para=usuario.email, erro=erro, remetente=settings.email_remetente
    )
