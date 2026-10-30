"""Atas de análise crítica (TREELE, 29/10/2026) — ver services/atas.py.

- ``POST /atas/pendentes``: das revisões que vão ser liberadas, as que ainda
  pedem ata, agrupadas por obra e disciplina, cada grupo com o formulário.
- ``POST /atas``: registra a ata de um grupo.
- ``GET /atas`` e ``GET /atas/{id}``: a lista (menu lateral) e a ata.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import montar_contexto, usuario_atual
from ..enums import StatusRevisao
from ..config import settings
from ..models import AtaAnalise, Obra, ObraMembro, Revisao, Usuario
from ..schemas import Pagina
from ..services import ata_pdf
from ..services import atas as servico
from ..services import auditoria
from .revisoes import _carregar

router = APIRouter(prefix="/atas", tags=["atas de análise crítica"])


class PendentesEntrada(BaseModel):
    revisao_ids: list[int] = Field(min_length=1, max_length=500)


class RevisaoDaAta(BaseModel):
    id: int
    documento: str
    titulo: str | None = None
    revisao: str


class GrupoPendente(BaseModel):
    obra_id: int
    obra: str
    disciplina: str
    disciplina_nome: str
    revisoes: list[RevisaoDaAta]
    formulario: dict


class Resposta(BaseModel):
    id: str
    resposta: str
    comentario: str | None = None


class AtaEntrada(BaseModel):
    revisao_ids: list[int] = Field(min_length=1, max_length=500)
    respostas: list[Resposta]
    observacoes: str | None = Field(default=None, max_length=8000)


class AtaLinha(BaseModel):
    id: int
    codigo: str
    obra_id: int
    obra: str
    disciplina: str
    disciplina_nome: str
    resultado: str
    revisoes: list[RevisaoDaAta]
    criada_por: str | None
    criada_em: datetime
    nao_conformes: int


class SituacaoRevisao(BaseModel):
    """A revisão hoje — a ata é de antes da decisão: a reprovação (motivo, quem,
    quando) e a revisão nova que trouxe a correção entram na "Solicitação de
    alterações" da ata."""

    id: int
    documento: str
    revisao: str
    status: str
    reprovada_em: datetime | None = None
    reprovada_por: str | None = None
    motivo: str | None = None
    recebida_em: datetime | None = None


class AtaOut(AtaLinha):
    obra_nome: str
    # "arquitetônico", "hidrossanitário"…: o título da ata (ENG-FL-001).
    adjetivo: str
    obra_endereco: str | None
    formulario: str
    titulo: str
    itens: list[dict]
    observacoes: str | None
    analisado_por: str
    situacao: list[SituacaoRevisao]


def _linha(ata: AtaAnalise) -> dict:
    return {
        "id": ata.id,
        "codigo": ata.codigo,
        "obra_id": ata.obra_id,
        "obra": ata.obra.codigo,
        "disciplina": ata.disciplina.codigo,
        "disciplina_nome": ata.disciplina.nome,
        "resultado": ata.resultado,
        "revisoes": [RevisaoDaAta(**{k: r[k] for k in ("id", "documento", "titulo", "revisao")}) for r in ata.revisoes_texto],
        "criada_por": ata.criada_por.nome if ata.criada_por else None,
        "criada_em": ata.criada_em,
        "nao_conformes": sum(1 for i in ata.itens if i.get("resposta") == "N"),
    }


def _situacao(db: Session, revisao) -> SituacaoRevisao:
    reprovada = revisao.status == StatusRevisao.reprovado
    seguinte = None
    if reprovada:
        # Recebimento da correção: a primeira revisão do documento depois desta.
        seguinte = db.scalar(
            select(Revisao)
            .where(Revisao.documento_id == revisao.documento_id, Revisao.ordem > revisao.ordem)
            .order_by(Revisao.ordem)
            .limit(1)
        )
    return SituacaoRevisao(
        id=revisao.id,
        documento=revisao.documento.codigo,
        revisao=revisao.numero,
        status=revisao.status.value,
        reprovada_em=revisao.reprovada_em if reprovada else None,
        reprovada_por=revisao.reprovada_por.nome if reprovada and revisao.reprovada_por else None,
        motivo=revisao.observacao if reprovada else None,
        recebida_em=seguinte.criada_em if seguinte else None,
    )


def _completa(db: Session, ata: AtaAnalise) -> AtaOut:
    return AtaOut(
        **_linha(ata),
        obra_nome=ata.obra.nome,
        adjetivo=servico.adjetivo(ata.disciplina.codigo, ata.disciplina.nome),
        obra_endereco=ata.obra.endereco,
        formulario=ata.formulario,
        titulo=servico.checklist()["titulo"],
        itens=ata.itens,
        observacoes=ata.observacoes,
        analisado_por=settings.ata_analisado_por,
        situacao=[_situacao(db, r) for r in ata.revisoes],
    )


def _carregar_grupo(db: Session, usuario: Usuario, ids: list[int]):
    """As revisões a analisar, conferidas: visíveis, em revisão e de quem pode
    liberar. Recusa a lista inteira se alguma não serve."""
    revisoes = []
    for revisao_id in dict.fromkeys(ids):
        revisao, ctx = _carregar(db, usuario, revisao_id)
        ctx.exigir("publicar", "Somente o coordenador da obra faz a análise crítica.")
        if revisao.status != StatusRevisao.em_revisao:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{revisao.documento.codigo} R{revisao.numero} está "
                f"{revisao.status.rotulo.lower()}: só revisão em revisão passa pela análise crítica.",
            )
        revisoes.append(revisao)
    return revisoes


@router.post("/pendentes", response_model=list[GrupoPendente])
def pendentes(
    dados: PendentesEntrada,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Das revisões a liberar, as que ainda pedem ata, por obra e disciplina:
    um formulário por grupo. As que não podem ser liberadas por outro motivo
    ficam de fora — a liberação as recusa com o motivo."""
    grupos: dict[tuple[int, int], GrupoPendente] = {}
    for revisao_id in dict.fromkeys(dados.revisao_ids):
        try:
            revisao, ctx = _carregar(db, usuario, revisao_id)
        except HTTPException:
            continue
        if (
            not ctx.pode("publicar")
            or revisao.status != StatusRevisao.em_revisao
            or not servico.precisa_de_ata(revisao)
        ):
            continue
        doc = revisao.documento
        chave = (doc.obra_id, doc.disciplina_id)
        if chave not in grupos:
            grupos[chave] = GrupoPendente(
                obra_id=doc.obra_id,
                obra=ctx.obra.codigo,
                disciplina=doc.disciplina.codigo,
                disciplina_nome=doc.disciplina.nome,
                revisoes=[],
                formulario=servico.formulario_da_disciplina(doc.disciplina.codigo),
            )
        grupos[chave].revisoes.append(
            RevisaoDaAta(id=revisao.id, documento=doc.codigo, titulo=doc.titulo, revisao=revisao.numero)
        )
    return list(grupos.values())


@router.post("", response_model=AtaOut, status_code=status.HTTP_201_CREATED)
def criar(
    dados: AtaEntrada,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    revisoes = _carregar_grupo(db, usuario, dados.revisao_ids)
    docs = {(r.documento.obra_id, r.documento.disciplina_id) for r in revisoes}
    if len(docs) > 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Uma ata cobre revisões de uma obra e de uma disciplina só.",
        )
    ja_tem = [r for r in revisoes if not servico.precisa_de_ata(r)]
    if ja_tem:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "mensagem": "Já existe ata de análise crítica conforme para estas revisões.",
                "erros": [f"{r.documento.codigo} R{r.numero}: {r.ata.codigo}" for r in ja_tem],
            },
        )
    try:
        ata = servico.criar(
            db, revisoes, usuario,
            {r.id: (r.resposta, r.comentario or "") for r in dados.respostas},
            dados.observacoes,
        )
    except servico.AtaInvalida as erro:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, {"mensagem": str(erro), "erros": erro.erros}
        ) from None
    auditoria.registrar(
        db, acao="ata_analise_registrada", entidade="ata_analise", entidade_id=ata.id,
        usuario=usuario, obra_id=ata.obra_id,
        detalhes={
            "ata": ata.codigo,
            "resultado": ata.resultado,
            "revisoes": [f"{r.documento.codigo} R{r.numero}" for r in revisoes],
        },
        request=request,
    )
    db.commit()
    db.refresh(ata)
    return _completa(db, ata)


def _obras_visiveis(db: Session, usuario: Usuario):
    """Atas são da equipe: o comercial não vê; o administrador vê todas."""
    if usuario.comercial and not usuario.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "O perfil comercial só consulta e baixa arquivos.")
    if usuario.admin or usuario.todas_obras:
        return None
    return select(ObraMembro.obra_id).where(ObraMembro.usuario_id == usuario.id)


@router.get("", response_model=Pagina[AtaLinha])
def listar(
    obra_id: int | None = None,
    disciplina_id: int | None = None,
    resultado: str | None = None,
    busca: str | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    consulta = select(AtaAnalise)
    obras = _obras_visiveis(db, usuario)
    if obras is not None:
        consulta = consulta.where(AtaAnalise.obra_id.in_(obras))
    if obra_id:
        consulta = consulta.where(AtaAnalise.obra_id == obra_id)
    if disciplina_id:
        consulta = consulta.where(AtaAnalise.disciplina_id == disciplina_id)
    if resultado in ("conforme", "nao_conforme"):
        consulta = consulta.where(AtaAnalise.resultado == resultado)
    if busca and busca.strip():
        # O código do documento está no texto das revisões (JSON); casar no
        # texto serializado é o que funciona igual no SQLite e no Postgres.
        termo = f"%{busca.strip().lower()}%"
        consulta = consulta.join(Obra, Obra.id == AtaAnalise.obra_id).where(
            func.lower(cast(AtaAnalise.revisoes_texto, Text)).like(termo)
            | func.lower(Obra.codigo).like(termo)
        )
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    por_pagina = max(1, min(por_pagina, 200))
    pagina = max(1, pagina)
    atas = db.scalars(
        consulta.order_by(AtaAnalise.criada_em.desc(), AtaAnalise.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return Pagina[AtaLinha](
        itens=[AtaLinha(**_linha(a)) for a in atas], total=total, pagina=pagina, por_pagina=por_pagina
    )


@router.get("/{ata_id}", response_model=AtaOut)
def detalhe(
    ata_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    ata = db.get(AtaAnalise, ata_id)
    if ata is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ata não encontrada.")
    ctx = montar_contexto(db, usuario, ata.obra_id)
    ctx.somente_equipe()
    return _completa(db, ata)


@router.get("/{ata_id}/pdf")
def pdf(
    ata_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """A ata em PDF, no modelo ENG-FL-001 (services/ata_pdf.py)."""
    ata = db.get(AtaAnalise, ata_id)
    if ata is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ata não encontrada.")
    ctx = montar_contexto(db, usuario, ata.obra_id)
    ctx.somente_equipe()
    conteudo = ata_pdf.gerar(_completa(db, ata).model_dump())
    return Response(
        conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{ata.codigo}.pdf"'},
    )
