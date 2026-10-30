from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import usuario_admin, usuario_atual
import secrets

from ..models import ObraMembro, Usuario
from ..schemas import AcessoAlterar, ObraDoUsuario, SenhaRedefinir, UsuarioComAcesso, UsuarioCriar, UsuarioOut
from ..security import gerar_hash_senha
from ..services import acesso, auditoria

router = APIRouter(prefix="/usuarios", tags=["usuários"])


def _com_acesso(db: Session, u: Usuario, com_obras: bool) -> UsuarioComAcesso:
    obras = []
    if com_obras:
        obras = [
            ObraDoUsuario(obra_id=m.obra_id, codigo=m.obra.codigo, papel=m.papel)
            for m in db.scalars(select(ObraMembro).where(ObraMembro.usuario_id == u.id))
        ]
        obras.sort(key=lambda o: o.codigo)
    return UsuarioComAcesso(
        id=u.id, nome=u.nome, email=u.email, admin=u.admin, comercial=u.comercial,
        todas_obras=u.todas_obras, ativo=u.ativo, tipo=acesso.tipo_de(u), obras=obras,
    )


@router.get("", response_model=list[UsuarioComAcesso])
def listar(
    incluir_inativos: bool = False,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Lista visível a qualquer autenticado — é preciso para montar equipe de obra.

    Menos o comercial: ele não monta equipe, e a lista traz o e-mail de todos.
    """
    if usuario.comercial:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "O perfil comercial só consulta e baixa arquivos."
        )
    consulta = select(Usuario).order_by(Usuario.nome)
    if not incluir_inativos:
        consulta = consulta.where(Usuario.ativo.is_(True))
    # As obras de cada um só para o administrador, que edita o acesso.
    return [_com_acesso(db, u, usuario.admin) for u in db.scalars(consulta)]


@router.post("", response_model=UsuarioComAcesso, status_code=status.HTTP_201_CREATED)
def criar(
    dados: UsuarioCriar,
    request: Request,
    admin: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    email = dados.email.lower()
    if dados.admin and dados.comercial:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Um usuário é administrador ou comercial, nunca os dois: o comercial "
            "existe justamente para ter o mínimo de acesso.",
        )
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Já existe um usuário com o e-mail {email}."
        )

    tipo = dados.tipo or ("administrador" if dados.admin else "comercial" if dados.comercial else "obra_especifica")
    usuario = Usuario(
        nome=dados.nome.strip(),
        email=email,
        # Sem senha: entra com a conta Microsoft (o login acha pelo e-mail); a
        # senha local fica uma que ninguém sabe.
        senha_hash=gerar_hash_senha(dados.senha or secrets.token_urlsafe(32)),
        admin=False,
        comercial=False,
    )
    db.add(usuario)
    db.flush()
    try:
        acesso.aplicar(db, usuario, tipo, dados.obras)
    except acesso.AcessoInvalido as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from None

    auditoria.registrar(
        db, acao="usuario_criado", entidade="usuario", entidade_id=usuario.id,
        usuario=admin, detalhes={"email": email, "tipo": tipo, "senha_local": bool(dados.senha)},
        request=request,
    )
    db.commit()
    return _com_acesso(db, usuario, True)


@router.patch("/{usuario_id}/acesso", response_model=UsuarioComAcesso)
def alterar_acesso(
    usuario_id: int,
    dados: AcessoAlterar,
    request: Request,
    admin: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    """Troca o tipo de acesso de quem já existe (TREELE, 30/10/2026)."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    if usuario.id == admin.id and dados.tipo != "administrador":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Você não pode tirar o seu próprio acesso de administrador.")
    antes = acesso.tipo_de(usuario)
    try:
        acesso.aplicar(db, usuario, dados.tipo, dados.obras)
    except acesso.AcessoInvalido as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from None
    auditoria.registrar(
        db, acao="usuario_acesso_alterado", entidade="usuario", entidade_id=usuario.id,
        usuario=admin, detalhes={"de": antes, "para": dados.tipo, "obras": dados.obras}, request=request,
    )
    db.commit()
    db.refresh(usuario)
    return _com_acesso(db, usuario, True)


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
    dados: SenhaRedefinir,
    request: Request,
    admin: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")

    usuario.senha_hash = gerar_hash_senha(dados.senha_nova)
    auditoria.registrar(
        db, acao="senha_redefinida", entidade="usuario", entidade_id=usuario.id,
        usuario=admin, request=request,
    )
    db.commit()
