"""Disciplinas e fases — os catálogos que a nomenclatura valida contra."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import usuario_admin, usuario_atual
from ..models import Disciplina, Documento, Fase, Usuario
from ..schemas import DisciplinaCriar, DisciplinaOut, FaseCriar, FaseOut

router = APIRouter(tags=["catálogos"])


@router.get("/disciplinas", response_model=list[DisciplinaOut])
def listar_disciplinas(
    incluir_inativas: bool = False,
    _: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    consulta = select(Disciplina).order_by(Disciplina.ordem, Disciplina.codigo)
    if not incluir_inativas:
        consulta = consulta.where(Disciplina.ativa.is_(True))
    return list(db.scalars(consulta))


@router.post(
    "/disciplinas", response_model=DisciplinaOut, status_code=status.HTTP_201_CREATED
)
def criar_disciplina(
    dados: DisciplinaCriar,
    _: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    codigo = dados.codigo.upper()
    if db.scalar(select(Disciplina).where(Disciplina.codigo == codigo)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A disciplina {codigo} já existe."
        )
    item = Disciplina(codigo=codigo, nome=dados.nome.strip(), ordem=dados.ordem)
    db.add(item)
    db.commit()
    return item


@router.patch("/disciplinas/{item_id}/ativa", response_model=DisciplinaOut)
def alternar_disciplina(
    item_id: int,
    ativa: bool,
    _: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    item = db.get(Disciplina, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Disciplina não encontrada.")

    if not ativa:
        em_uso = db.scalar(
            select(Documento.id).where(Documento.disciplina_id == item_id).limit(1)
        )
        if em_uso:
            # Desativar só impede novos envios; o acervo existente continua válido.
            item.ativa = False
            db.commit()
            return item

    item.ativa = ativa
    db.commit()
    return item


@router.get("/fases", response_model=list[FaseOut])
def listar_fases(
    incluir_inativas: bool = False,
    _: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    consulta = select(Fase).order_by(Fase.ordem, Fase.codigo)
    if not incluir_inativas:
        consulta = consulta.where(Fase.ativa.is_(True))
    return list(db.scalars(consulta))


@router.post("/fases", response_model=FaseOut, status_code=status.HTTP_201_CREATED)
def criar_fase(
    dados: FaseCriar,
    _: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    codigo = dados.codigo.upper()
    if db.scalar(select(Fase).where(Fase.codigo == codigo)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A fase {codigo} já existe.")
    item = Fase(codigo=codigo, nome=dados.nome.strip(), ordem=dados.ordem)
    db.add(item)
    db.commit()
    return item


@router.patch("/fases/{item_id}/ativa", response_model=FaseOut)
def alternar_fase(
    item_id: int,
    ativa: bool,
    _: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    item = db.get(Fase, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fase não encontrada.")
    item.ativa = ativa
    db.commit()
    return item
