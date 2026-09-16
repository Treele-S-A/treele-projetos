from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import usuario_admin, usuario_atual
from ..models import Usuario
from ..schemas import UsuarioCriar, UsuarioOut
from ..security import gerar_hash_senha
from ..services import auditoria

router = APIRouter(prefix="/usuarios", tags=["usuários"])


@router.get("", response_model=list[UsuarioOut])
def listar(
    incluir_inativos: bool = False,
    _: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Lista visível a qualquer autenticado — é preciso para montar equipe de obra."""
    consulta = select(Usuario).order_by(Usuario.nome)
    if not incluir_inativos:
        consulta = consulta.where(Usuario.ativo.is_(True))
    return list(db.scalars(consulta))


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar(
    dados: UsuarioCriar,
    request: Request,
    admin: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    email = dados.email.lower()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Já existe um usuário com o e-mail {email}."
        )

    usuario = Usuario(
        nome=dados.nome.strip(),
        email=email,
        senha_hash=gerar_hash_senha(dados.senha),
        admin=dados.admin,
    )
    db.add(usuario)
    db.flush()

    auditoria.registrar(
        db, acao="usuario_criado", entidade="usuario", entidade_id=usuario.id,
        usuario=admin, detalhes={"email": email}, request=request,
    )
    db.commit()
    return usuario


@router.patch("/{usuario_id}/ativo", response_model=UsuarioOut)
def alternar_ativo(
    usuario_id: int,
    ativo: bool,
    request: Request,
    admin: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    if usuario.id == admin.id and not ativo:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Você não pode desativar a si mesmo."
        )

    usuario.ativo = ativo
    auditoria.registrar(
        db,
        acao="usuario_ativado" if ativo else "usuario_desativado",
        entidade="usuario", entidade_id=usuario.id, usuario=admin, request=request,
    )
    db.commit()
    return usuario


@router.post("/{usuario_id}/senha", status_code=status.HTTP_204_NO_CONTENT)
def redefinir_senha(
    usuario_id: int,
    senha_nova: str,
    request: Request,
    admin: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    if len(senha_nova) < 8:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "A senha precisa ter ao menos 8 caracteres."
        )
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")

    usuario.senha_hash = gerar_hash_senha(senha_nova)
    auditoria.registrar(
        db, acao="senha_redefinida", entidade="usuario", entidade_id=usuario.id,
        usuario=admin, request=request,
    )
    db.commit()
