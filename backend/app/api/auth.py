from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import usuario_atual
from ..models import Usuario
from ..schemas import LoginEntrada, SenhaAlterar, TokenSaida, UsuarioOut
from ..security import conferir_senha, criar_token, gerar_hash_senha
from ..services import auditoria

router = APIRouter(prefix="/auth", tags=["autenticação"])


@router.post("/login", response_model=TokenSaida)
def login(dados: LoginEntrada, request: Request, db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.email == dados.email.lower()))

    if (
        usuario is None
        or not usuario.ativo
        or not conferir_senha(dados.senha, usuario.senha_hash)
    ):
        # Mensagem única de propósito: não revela se o e-mail existe.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos.")

    auditoria.registrar(
        db, acao="login", entidade="usuario", entidade_id=usuario.id,
        usuario=usuario, request=request,
    )
    db.commit()

    return TokenSaida(
        token=criar_token(usuario.id),
        expira_em_minutos=settings.token_expira_minutos,
    )


@router.get("/eu", response_model=UsuarioOut)
def eu(usuario: Usuario = Depends(usuario_atual)):
    return usuario


@router.post("/senha", status_code=status.HTTP_204_NO_CONTENT)
def alterar_senha(
    dados: SenhaAlterar,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    if not conferir_senha(dados.senha_atual, usuario.senha_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha atual incorreta.")

    usuario.senha_hash = gerar_hash_senha(dados.senha_nova)
    auditoria.registrar(
        db, acao="senha_alterada", entidade="usuario", entidade_id=usuario.id,
        usuario=usuario, request=request,
    )
    db.commit()
