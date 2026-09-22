"""Dependências de rota: usuário autenticado, obra em contexto e permissões."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .enums import PERMISSOES, PapelObra, StatusRevisao
from .models import Disciplina, Fase, Obra, ObraMembro, PadraoNomenclatura, Usuario
from .security import ler_token

esquema = HTTPBearer(auto_error=False)


def usuario_atual(
    credencial: HTTPAuthorizationCredentials | None = Depends(esquema),
    db: Session = Depends(get_db),
) -> Usuario:
    if credencial is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Autenticação necessária.")

    usuario_id = ler_token(credencial.credentials)
    if usuario_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada ou inválida.")

    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário inativo.")
    return usuario


def usuario_admin(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    if not usuario.admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Somente um administrador pode fazer isso."
        )
    return usuario


@dataclass
class ContextoObra:
    usuario: Usuario
    obra: Obra
    papel: PapelObra | None
    permissoes: set[str]
    db: Session

    def pode(self, permissao: str) -> bool:
        return self.usuario.admin or permissao in self.permissoes

    def exigir(self, permissao: str, mensagem: str | None = None) -> None:
        if not self.pode(permissao):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                mensagem
                or f"Seu papel nesta obra ({self.papel.rotulo if self.papel else '—'}) "
                "não permite esta ação.",
            )


def montar_contexto(db: Session, usuario: Usuario, obra_id: int) -> ContextoObra:
    """Resolve obra + papel. Usado pelas rotas que não têm obra_id no caminho
    (download de arquivo, publicação de revisão) e chegam à obra pelo objeto."""
    obra = db.get(Obra, obra_id)
    if obra is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Obra não encontrada.")

    membro = db.scalar(
        select(ObraMembro).where(
            ObraMembro.obra_id == obra_id, ObraMembro.usuario_id == usuario.id
        )
    )
    if membro is None and not usuario.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Você não participa desta obra.")

    papel = membro.papel if membro else None
    permissoes = set(PERMISSOES.get(papel, set())) if papel else set()
    return ContextoObra(
        usuario=usuario, obra=obra, papel=papel, permissoes=permissoes, db=db
    )


def contexto_obra(
    obra_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> ContextoObra:
    return montar_contexto(db, usuario, obra_id)


def status_visiveis(ctx: ContextoObra) -> list[StatusRevisao]:
    """Quais status de revisão este papel pode enxergar.

    Um só lugar decide isso. Espalhar a regra por cada endpoint é como uma
    tela acaba mostrando o que outra esconde.
    """
    visiveis = [StatusRevisao.liberado_para_obra]
    if ctx.pode("ver_obsoletos"):
        visiveis.append(StatusRevisao.obsoleto)
    if ctx.pode("ver_em_revisao"):
        visiveis.append(StatusRevisao.em_revisao)
        visiveis.append(StatusRevisao.cancelado)
    return visiveis


# --------------------------------------------------------------------------
# Catálogos em contexto
# --------------------------------------------------------------------------


def padrao_da_obra(db: Session, obra_id: int) -> PadraoNomenclatura:
    """Padrão específico da obra; se ela não tiver, o padrão global."""
    padrao = db.scalar(
        select(PadraoNomenclatura).where(
            PadraoNomenclatura.obra_id == obra_id,
            PadraoNomenclatura.ativo.is_(True),
        )
    )
    if padrao is not None:
        return padrao

    global_ = db.scalar(
        select(PadraoNomenclatura).where(
            PadraoNomenclatura.obra_id.is_(None),
            PadraoNomenclatura.ativo.is_(True),
        )
    )
    if global_ is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Nenhum padrão de nomenclatura está configurado. "
            "Defina um antes de enviar arquivos.",
        )
    return global_


def codigos_disciplinas(db: Session) -> set[str]:
    return {
        c.upper()
        for c in db.scalars(
            select(Disciplina.codigo).where(Disciplina.ativa.is_(True))
        )
    }


def codigos_fases(db: Session) -> set[str]:
    return {
        c.upper()
        for c in db.scalars(select(Fase.codigo).where(Fase.ativa.is_(True)))
    }
