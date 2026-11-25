"""Atas de mudança de projeto (TREELE, 25/11/2026), no módulo Qualidade.

Registram uma alteração técnica adotada: não são as atas de análise crítica
(PRO-FL-005). São PDFs que o coordenador sobe com qualquer nome, dizendo a obra
e a disciplina; o sistema dá o nome na ordem em que chegam:

    SER-HID-AMP01-R00, SER-HID-AMP01-R01, SER-HID-AMP02-R00, MIL-ARQ-AMP01-R00

Cada ata aceita revisões (R01, R02…). Quem vê e mexe: os coordenadores da obra
(o administrador coordena todas), como no cronograma.

O PDF sobe direto para o armazenamento, como os arquivos de projeto: a rota
cria o envio (pendente) e devolve a URL assinada; ao confirmar a chegada, o
envio ganha número. Excluir apaga de vez a revisão (ou a ata inteira) e o
arquivo; o número só volta a ser usado se era o último.
"""

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ContextoObra, contexto_obra, montar_contexto, usuario_atual
from ..enums import PapelObra, StatusArquivo
from ..models import AtaMudanca, AtaMudancaRevisao, Disciplina, Obra, ObraMembro, Usuario
from ..services import auditoria
from ..services.storage import _ascii_seguro, armazenamento

router = APIRouter(tags=["atas de mudança de projeto"])

SO_COORDENADOR = "As atas de mudança de projeto são dos coordenadores da obra."
MAX_MB = 50


class EnvioEntrada(BaseModel):
    nome_arquivo: str = Field(min_length=1, max_length=300)
    tamanho: int = Field(ge=1)
    # Ata nova: a disciplina (e um assunto opcional). Revisão: a ata.
    disciplina_id: int | None = None
    ata_id: int | None = None
    assunto: str | None = Field(default=None, max_length=300)


class EnvioSaida(BaseModel):
    envio_id: int
    url: str
    metodo: str
    headers: dict[str, str]


class RevisaoOut(BaseModel):
    id: int
    numero: int
    codigo: str
    nome_original: str
    tamanho: int
    enviada_em: datetime
    enviada_por: str | None


class AtaOut(BaseModel):
    id: int
    obra_id: int
    disciplina: str
    disciplina_nome: str
    numero: int
    codigo: str
    assunto: str | None
    criada_em: datetime
    revisoes: list[RevisaoOut]


class AssuntoEntrada(BaseModel):
    assunto: str | None = Field(default=None, max_length=300)


def _exigir(ctx: ContextoObra) -> None:
    ctx.exigir("gerenciar", SO_COORDENADOR)


def codigo(obra: Obra, disciplina: Disciplina, numero: int, revisao: int | None = None) -> str:
    base = f"{obra.codigo}-{disciplina.codigo}-AMP{numero:02d}"
    return base if revisao is None else f"{base}-R{revisao:02d}"


def _revisoes(ata: AtaMudanca) -> list[AtaMudancaRevisao]:
    return [r for r in ata.revisoes if r.status == StatusArquivo.disponivel and r.numero is not None]


def _saida(ata: AtaMudanca) -> AtaOut:
    return AtaOut(
        id=ata.id, obra_id=ata.obra_id, disciplina=ata.disciplina.codigo, disciplina_nome=ata.disciplina.nome,
        numero=ata.numero, codigo=codigo(ata.obra, ata.disciplina, ata.numero), assunto=ata.assunto,
        criada_em=ata.criada_em,
        revisoes=[
            RevisaoOut(
                id=r.id, numero=r.numero, codigo=codigo(ata.obra, ata.disciplina, ata.numero, r.numero),
                nome_original=r.nome_original, tamanho=r.tamanho, enviada_em=r.enviada_em,
                enviada_por=r.enviada_por.nome if r.enviada_por else None,
            )
            for r in _revisoes(ata)
        ],
    )


def _ata(db: Session, usuario: Usuario, ata_id: int) -> tuple[AtaMudanca, ContextoObra]:
    ata = db.get(AtaMudanca, ata_id)
    if ata is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ata de mudança não encontrada.")
    ctx = montar_contexto(db, usuario, ata.obra_id)
    _exigir(ctx)
    return ata, ctx


def _revisao(db: Session, usuario: Usuario, revisao_id: int) -> tuple[AtaMudancaRevisao, ContextoObra]:
    rev = db.get(AtaMudancaRevisao, revisao_id)
    if rev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo não encontrado.")
    ctx = montar_contexto(db, usuario, rev.obra_id)
    _exigir(ctx)
    return rev, ctx


@router.get("/atas-mudanca/obras")
def obras(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """As obras que a pessoa coordena, com quantas atas cada uma tem."""
    if usuario.admin:
        lista = list(db.scalars(select(Obra).where(Obra.ativa.is_(True)).order_by(Obra.codigo)))
    else:
        lista = list(db.scalars(
            select(Obra).join(ObraMembro, ObraMembro.obra_id == Obra.id)
            .where(ObraMembro.usuario_id == usuario.id, ObraMembro.papel == PapelObra.coordenador,
                   Obra.ativa.is_(True))
            .order_by(Obra.codigo)
        ))
    contagem = dict(db.execute(
        select(AtaMudanca.obra_id, func.count(AtaMudanca.id))
        .where(AtaMudanca.obra_id.in_([o.id for o in lista]))
        .group_by(AtaMudanca.obra_id)
    ).all())
    return [{"id": o.id, "codigo": o.codigo, "nome": o.nome, "atas": contagem.get(o.id, 0)} for o in lista]


@router.get("/obras/{obra_id}/atas-mudanca", response_model=list[AtaOut])
def listar(ctx: ContextoObra = Depends(contexto_obra), db: Session = Depends(get_db)):
    """As atas da obra, por disciplina e número, com as revisões."""
    _exigir(ctx)
    atas = db.scalars(
        select(AtaMudanca).join(Disciplina, Disciplina.id == AtaMudanca.disciplina_id)
        .where(AtaMudanca.obra_id == ctx.obra.id)
        .order_by(Disciplina.ordem, Disciplina.codigo, AtaMudanca.numero)
    ).all()
    return [_saida(a) for a in atas if _revisoes(a)]


@router.post("/obras/{obra_id}/atas-mudanca/envios", response_model=EnvioSaida, status_code=status.HTTP_201_CREATED)
def iniciar_envio(
    dados: EnvioEntrada,
    ctx: ContextoObra = Depends(contexto_obra),
    db: Session = Depends(get_db),
):
    _exigir(ctx)
    if not dados.nome_arquivo.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Envie a ata em PDF.")
    if dados.tamanho > MAX_MB * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"A ata pode ter até {MAX_MB} MB.")
    if dados.ata_id is not None:
        ata = db.get(AtaMudanca, dados.ata_id)
        if ata is None or ata.obra_id != ctx.obra.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ata de mudança não encontrada nesta obra.")
        disciplina_id = ata.disciplina_id
    else:
        disciplina = db.get(Disciplina, dados.disciplina_id) if dados.disciplina_id else None
        if disciplina is None or not disciplina.ativa:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escolha a disciplina da ata.")
        disciplina_id = disciplina.id
    chave = "/".join([
        "obras", _ascii_seguro(ctx.obra.codigo), "_atas_mudanca",
        f"{secrets.token_hex(8)}-{_ascii_seguro(dados.nome_arquivo)}",
    ])
    envio = AtaMudancaRevisao(
        ata_id=dados.ata_id, obra_id=ctx.obra.id, disciplina_id=disciplina_id,
        assunto=((dados.assunto or "").strip() or None) if dados.ata_id is None else None,
        nome_original=dados.nome_arquivo, storage_key=chave, tamanho=0, enviada_por_id=ctx.usuario.id,
    )
    db.add(envio)
    db.flush()
    destino = armazenamento.destino_upload(chave, "application/pdf")
    db.commit()
    return EnvioSaida(envio_id=envio.id, url=destino.url, metodo=destino.metodo, headers=destino.headers)


@router.post("/atas-mudanca/envios/{envio_id}/confirmar", response_model=AtaOut)
def confirmar_envio(
    envio_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """O PDF chegou: dá o número (da ata nova e da revisão) e o nome."""
    envio, ctx = _revisao(db, usuario, envio_id)
    if envio.status == StatusArquivo.disponivel:
        return _saida(envio.ata)
    existe, tamanho = armazenamento.info(envio.storage_key)
    if not existe:
        envio.status = StatusArquivo.erro
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "A ata não chegou ao armazenamento. Tente de novo.")
    if tamanho > MAX_MB * 1024 * 1024:
        armazenamento.remover(envio.storage_key)
        db.delete(envio)
        db.commit()
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"A ata pode ter até {MAX_MB} MB.")

    nova = envio.ata_id is None
    if nova:
        numero = (db.scalar(
            select(func.max(AtaMudanca.numero))
            .where(AtaMudanca.obra_id == envio.obra_id, AtaMudanca.disciplina_id == envio.disciplina_id)
        ) or 0) + 1
        ata = AtaMudanca(obra_id=envio.obra_id, disciplina_id=envio.disciplina_id, numero=numero,
                         assunto=envio.assunto, criada_por_id=usuario.id)
        db.add(ata)
        db.flush()
        envio.ata_id = ata.id
        envio.numero = 0
    else:
        ata = envio.ata
        ultima = db.scalar(select(func.max(AtaMudancaRevisao.numero)).where(AtaMudancaRevisao.ata_id == ata.id))
        envio.numero = 0 if ultima is None else ultima + 1
    envio.status = StatusArquivo.disponivel
    envio.tamanho = tamanho
    db.flush()
    db.refresh(ata)
    nome = codigo(ata.obra, ata.disciplina, ata.numero, envio.numero)
    auditoria.registrar(
        db, acao="ata_mudanca_enviada", entidade="ata_mudanca", entidade_id=ata.id, usuario=usuario,
        obra_id=ata.obra_id, detalhes={"ata": nome, "arquivo": envio.nome_original, "nova": nova}, request=request,
    )
    db.commit()
    db.refresh(ata)
    return _saida(ata)


@router.get("/atas-mudanca/revisoes/{revisao_id}/visualizar")
def visualizar(
    revisao_id: int,
    baixar: bool = False,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """URL assinada para abrir (ou baixar) o PDF, já com o nome do sistema."""
    rev, _ = _revisao(db, usuario, revisao_id)
    if rev.status != StatusArquivo.disponivel or rev.ata is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo não encontrado.")
    nome = codigo(rev.ata.obra, rev.ata.disciplina, rev.ata.numero, rev.numero) + ".pdf"
    url = armazenamento.url_download(rev.storage_key, nome) if baixar else armazenamento.url_visualizar(rev.storage_key, nome)
    return {"url": url, "nome": nome}


@router.patch("/atas-mudanca/{ata_id}", response_model=AtaOut)
def mudar_assunto(
    ata_id: int, dados: AssuntoEntrada, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)
):
    ata, _ = _ata(db, usuario, ata_id)
    ata.assunto = (dados.assunto or "").strip() or None
    db.commit()
    db.refresh(ata)
    return _saida(ata)


@router.delete("/atas-mudanca/revisoes/{revisao_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_revisao(
    revisao_id: int, request: Request, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)
):
    """Apaga uma revisão e o PDF dela. Era a única: a ata sai junto."""
    rev, _ = _revisao(db, usuario, revisao_id)
    ata = rev.ata
    if ata is None or rev.status != StatusArquivo.disponivel:
        armazenamento.remover(rev.storage_key)
        db.delete(rev)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    nome = codigo(ata.obra, ata.disciplina, ata.numero, rev.numero)
    armazenamento.remover(rev.storage_key)
    db.delete(rev)
    db.flush()
    db.refresh(ata)
    sobra = bool(_revisoes(ata))
    if not sobra:
        for r in list(ata.revisoes):
            armazenamento.remover(r.storage_key)
        db.delete(ata)
    auditoria.registrar(
        db, acao="ata_mudanca_excluida", entidade="ata_mudanca", entidade_id=ata.id, usuario=usuario,
        obra_id=ata.obra_id, detalhes={"revisao": nome, "ata_inteira": not sobra}, request=request,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/atas-mudanca/{ata_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_ata(
    ata_id: int, request: Request, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)
):
    """Apaga a ata com todas as revisões e os PDFs."""
    ata, _ = _ata(db, usuario, ata_id)
    nome = codigo(ata.obra, ata.disciplina, ata.numero)
    revisoes = [codigo(ata.obra, ata.disciplina, ata.numero, r.numero) for r in _revisoes(ata)]
    for r in list(ata.revisoes):
        armazenamento.remover(r.storage_key)
    obra_id = ata.obra_id
    db.delete(ata)
    auditoria.registrar(
        db, acao="ata_mudanca_excluida", entidade="ata_mudanca", entidade_id=ata_id, usuario=usuario,
        obra_id=obra_id, detalhes={"ata": nome, "revisoes": revisoes, "ata_inteira": True}, request=request,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
