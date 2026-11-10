"""Controle de acessos (TREELE, 10/11/2026): cada vez que alguém entra no
sistema, com horário e dispositivo, numa tela dos coordenadores.

Entrar conta de três jeitos: login com senha, login pela Microsoft e a volta de
quem já estava conectado (a sessão de 30 dias não pede login de novo, mas a
pessoa abriu o sistema). A volta é avisada pela tela ao abrir e ao reaparecer,
e vale uma vez a cada 30 minutos: abrir e fechar abas não enche a lista.

O administrador vê todo mundo; o coordenador, as pessoas das obras que ele
coordena. Os registros são eventos da trilha de auditoria (sem obra) e, como
ela, nunca são apagados."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import usuario_atual
from ..enums import PapelObra
from ..models import Evento, ObraMembro, Usuario
from ..services import auditoria

router = APIRouter(tags=["acessos"])

ACOES = ("login", "acesso")
INTERVALO = timedelta(minutes=30)


class PessoaOut(BaseModel):
    id: int
    nome: str
    email: str
    ativo: bool


class AcessoOut(BaseModel):
    id: int
    usuario: PessoaOut
    quando: datetime
    tipo: str  # login_senha, login_microsoft ou retorno
    dispositivo: str | None


class ResumoOut(BaseModel):
    usuario: PessoaOut
    ultimo: datetime | None
    no_periodo: int


class AcessosOut(BaseModel):
    pessoas: list[ResumoOut]
    itens: list[AcessoOut]
    total: int
    pagina: int
    por_pagina: int


def _agora() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/auth/acesso", status_code=status.HTTP_204_NO_CONTENT)
def registrar_acesso(request: Request, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """A tela avisa que a pessoa abriu o sistema com a sessão guardada."""
    recente = db.scalar(
        select(Evento.id).where(
            Evento.usuario_id == usuario.id,
            Evento.acao.in_(ACOES),
            Evento.criado_em >= _agora() - INTERVALO,
        ).limit(1)
    )
    if recente is None:
        auditoria.registrar(
            db, acao="acesso", entidade="usuario", entidade_id=usuario.id, usuario=usuario,
            detalhes={"dispositivo": auditoria.dispositivo(request)}, request=request,
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _visiveis(db: Session, usuario: Usuario) -> set[int] | None:
    """Quem esta pessoa pode acompanhar. None = todo mundo (administrador)."""
    if usuario.admin:
        return None
    coordena = select(ObraMembro.obra_id).where(
        ObraMembro.usuario_id == usuario.id, ObraMembro.papel == PapelObra.coordenador
    )
    if db.scalar(select(func.count()).select_from(coordena.subquery())) == 0:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "O controle de acessos é dos coordenadores.")
    return set(db.scalars(select(ObraMembro.usuario_id).where(ObraMembro.obra_id.in_(coordena))))


def _pessoa(u: Usuario) -> PessoaOut:
    return PessoaOut(id=u.id, nome=u.nome, email=u.email, ativo=u.ativo)


def _tipo(e: Evento) -> str:
    if e.acao == "acesso":
        return "retorno"
    return "login_microsoft" if (e.detalhes or {}).get("metodo") == "microsoft" else "login_senha"


@router.get("/acessos", response_model=AcessosOut)
def listar_acessos(
    usuario_id: int | None = None,
    dias: int | None = Query(30, ge=1, le=3650),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    visiveis = _visiveis(db, usuario)
    if usuario_id is not None and visiveis is not None and usuario_id not in visiveis:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pessoa não encontrada na equipe das suas obras.")

    pessoas_q = select(Usuario).order_by(Usuario.nome)
    if visiveis is not None:
        pessoas_q = pessoas_q.where(Usuario.id.in_(visiveis))
    pessoas = list(db.scalars(pessoas_q))
    ids = [p.id for p in pessoas]

    condicoes = [Evento.acao.in_(ACOES), Evento.usuario_id.in_(ids)]
    if dias:
        condicoes.append(Evento.criado_em >= _agora() - timedelta(days=dias))
    base = select(Evento).where(*condicoes)

    ultimo = dict(db.execute(
        select(Evento.usuario_id, func.max(Evento.criado_em))
        .where(Evento.acao.in_(ACOES), Evento.usuario_id.in_(ids))
        .group_by(Evento.usuario_id)
    ).all())
    contagem = dict(db.execute(
        select(Evento.usuario_id, func.count(Evento.id))
        .where(*condicoes)
        .group_by(Evento.usuario_id)
    ).all())

    lista = base.where(Evento.usuario_id == usuario_id) if usuario_id is not None else base
    total = db.scalar(select(func.count()).select_from(lista.subquery())) or 0
    eventos = db.scalars(
        lista.order_by(Evento.criado_em.desc(), Evento.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina)
    ).all()
    por_id = {p.id: p for p in pessoas}

    resumo = [ResumoOut(usuario=_pessoa(p), ultimo=ultimo.get(p.id), no_periodo=contagem.get(p.id, 0)) for p in pessoas]
    # Quem entrou por último primeiro; quem nunca entrou, no fim.
    resumo.sort(key=lambda r: (r.ultimo is None, -(r.ultimo.timestamp() if r.ultimo else 0)))
    return AcessosOut(
        pessoas=resumo,
        itens=[AcessoOut(id=e.id, usuario=_pessoa(por_id[e.usuario_id]), quando=e.criado_em, tipo=_tipo(e),
                         dispositivo=(e.detalhes or {}).get("dispositivo")) for e in eventos],
        total=total, pagina=pagina, por_pagina=por_pagina,
    )
