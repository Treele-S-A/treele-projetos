"""Catálogo de documentos — a "lista mestra" da obra.

A revisão atual de um documento é a de maior ordem que não foi cancelada. O
status dela é o status do documento: se a maior revisão está "em revisão", o
documento tem pendência; se está "liberado para obra", é o que vale em campo.
"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from ..db import get_db
from ..deps import (
    ContextoObra,
    contexto_obra,
    montar_contexto,
    status_visiveis,
    usuario_atual,
)
from ..enums import StatusArquivo, StatusRevisao, TipoArquivo
from ..models import Arquivo, Disciplina, Documento, Fase, Revisao, Usuario
from ..schemas import (
    ArvoreSaida,
    CatalogoResumo,
    DocumentoAtualizar,
    DocumentoDetalhe,
    DocumentoOut,
    NoDisciplina,
    NoFase,
    NoTipo,
    Pagina,
    PastaSaida,
    RevisaoOut,
    RevisaoResumo,
)
from ..services import auditoria

router = APIRouter(tags=["documentos"])


def _subconsulta_atual():
    """(documento_id, ordem da revisão atual)."""
    return (
        select(
            Revisao.documento_id.label("doc_id"),
            func.max(Revisao.ordem).label("max_ordem"),
        )
        .where(Revisao.status != StatusRevisao.cancelado)
        .group_by(Revisao.documento_id)
        .subquery()
    )


def _consulta_base(obra_id: int):
    sub = _subconsulta_atual()
    atual = aliased(Revisao)
    consulta = (
        select(Documento, atual)
        .join(sub, sub.c.doc_id == Documento.id)
        .join(
            atual,
            and_(atual.documento_id == Documento.id, atual.ordem == sub.c.max_ordem),
        )
        .where(Documento.obra_id == obra_id)
    )
    return consulta, atual


def _aplicar_filtros(
    consulta,
    atual,
    *,
    disciplina_id: int | None,
    fase_id: int | None,
    status_revisao: StatusRevisao | None,
    tipo: TipoArquivo | None,
    busca: str | None,
):
    if disciplina_id:
        consulta = consulta.where(Documento.disciplina_id == disciplina_id)
    if fase_id:
        consulta = consulta.where(Documento.fase_id == fase_id)
    if status_revisao:
        consulta = consulta.where(atual.status == status_revisao)
    if tipo:
        consulta = consulta.where(
            select(Arquivo.id)
            .join(Revisao, Revisao.id == Arquivo.revisao_id)
            .where(Revisao.documento_id == Documento.id, Arquivo.tipo == tipo)
            .exists()
        )
    if busca:
        alvo = f"%{busca.strip()}%"
        consulta = consulta.where(
            or_(Documento.codigo.ilike(alvo), Documento.titulo.ilike(alvo))
        )
    return consulta


def _montar_saida(db: Session, linhas) -> list[DocumentoOut]:
    if not linhas:
        return []
    ids = [d.id for d, _ in linhas]
    contagens = dict(
        db.execute(
            select(Revisao.documento_id, func.count(Revisao.id))
            .where(Revisao.documento_id.in_(ids))
            .group_by(Revisao.documento_id)
        ).all()
    )
    saida = []
    for documento, atual in linhas:
        item = DocumentoOut.model_validate(documento)
        item.total_revisoes = contagens.get(documento.id, 0)
        item.revisao_atual = RevisaoResumo.model_validate(atual)
        saida.append(item)
    return saida


@router.get("/obras/{obra_id}/documentos", response_model=Pagina[DocumentoOut])
def listar(
    disciplina_id: int | None = None,
    fase_id: int | None = None,
    status_revisao: StatusRevisao | None = None,
    tipo: TipoArquivo | None = None,
    busca: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    ctx: ContextoObra = Depends(contexto_obra),
):
    consulta, atual = _consulta_base(ctx.obra.id)
    consulta = _aplicar_filtros(
        consulta, atual,
        disciplina_id=disciplina_id, fase_id=fase_id,
        status_revisao=status_revisao, tipo=tipo, busca=busca,
    )

    consulta = consulta.where(atual.status.in_(status_visiveis(ctx)))

    total = ctx.db.scalar(
        select(func.count()).select_from(consulta.order_by(None).subquery())
    )

    linhas = ctx.db.execute(
        consulta.order_by(Documento.codigo)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()

    return Pagina[DocumentoOut](
        itens=_montar_saida(ctx.db, linhas),
        total=total or 0,
        pagina=pagina,
        por_pagina=por_pagina,
    )


@router.get("/obras/{obra_id}/documentos/exportar")
def exportar(
    disciplina_id: int | None = None,
    fase_id: int | None = None,
    status_revisao: StatusRevisao | None = None,
    request: Request = None,
    ctx: ContextoObra = Depends(contexto_obra),
):
    """Lista mestra em CSV — o relatório que sempre pedem em reunião."""
    consulta, atual = _consulta_base(ctx.obra.id)
    consulta = _aplicar_filtros(
        consulta, atual,
        disciplina_id=disciplina_id, fase_id=fase_id,
        status_revisao=status_revisao, tipo=None, busca=None,
    )
    consulta = consulta.where(atual.status.in_(status_visiveis(ctx)))

    linhas = ctx.db.execute(consulta.order_by(Documento.codigo)).all()

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(
        [
            "Código", "Título", "Disciplina", "Fase",
            "Revisão atual", "Status", "Publicada em",
            "Total de revisões", "Arquivos",
        ]
    )
    for documento, revisao in linhas:
        arquivos = ", ".join(sorted({a.tipo.value.upper() for a in revisao.arquivos}))
        escritor.writerow(
            [
                documento.codigo,
                documento.titulo or "",
                documento.disciplina.codigo,
                documento.fase.codigo,
                f"R{revisao.numero}",
                revisao.status.rotulo,
                revisao.publicada_em.strftime("%d/%m/%Y %H:%M")
                if revisao.publicada_em
                else "",
                len(documento.revisoes),
                arquivos,
            ]
        )

    auditoria.registrar(
        ctx.db, acao="lista_mestra_exportada", entidade="obra",
        entidade_id=ctx.obra.id, usuario=ctx.usuario, obra_id=ctx.obra.id,
        detalhes={"linhas": len(linhas)}, request=request,
    )
    ctx.db.commit()

    nome = f"lista-mestra-{ctx.obra.codigo}-{datetime.now():%Y%m%d}.csv"
    # BOM para o Excel brasileiro abrir com acentuação correta.
    conteudo = "﻿" + buffer.getvalue()
    return StreamingResponse(
        iter([conteudo]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


# --------------------------------------------------------------------------
# Árvore do acervo
# --------------------------------------------------------------------------

# Ordem de exibição dos formatos: primeiro o que se edita, depois o que se lê.
ORDEM_TIPOS = {
    TipoArquivo.dwg: 0,
    TipoArquivo.rvt: 1,
    TipoArquivo.ifc: 2,
    TipoArquivo.pdf: 3,
    TipoArquivo.outro: 4,
}


@router.get("/obras/{obra_id}/arvore", response_model=ArvoreSaida)
def arvore(
    todas_revisoes: bool = False,
    ctx: ContextoObra = Depends(contexto_obra),
):
    """O acervo como árvore de pastas: Disciplina → Fase → Formato → Arquivos.

    A tabela plana serve para procurar; a árvore serve para navegar e para ver
    de relance o que cada disciplina já entregou. Por padrão mostra só a revisão
    vigente de cada documento — é isso que "o acervo" significa no dia a dia.
    `todas_revisoes=true` traz o histórico inteiro.

    Monta tudo numa consulta e agrupa em memória: o número de arquivos por obra
    é da ordem de milhares, não de milhões, e a árvore só é útil inteira.
    """
    atual = aliased(Revisao)
    consulta = (
        select(Arquivo, atual, Documento, Disciplina, Fase)
        .join(atual, atual.id == Arquivo.revisao_id)
        .join(Documento, Documento.id == atual.documento_id)
        .join(Disciplina, Disciplina.id == Documento.disciplina_id)
        .join(Fase, Fase.id == Documento.fase_id)
        .where(
            Documento.obra_id == ctx.obra.id,
            Arquivo.status == StatusArquivo.disponivel,
        )
    )

    if todas_revisoes:
        consulta = consulta.where(atual.status != StatusRevisao.cancelado)
    else:
        sub = _subconsulta_atual()
        consulta = consulta.join(
            sub,
            and_(sub.c.doc_id == Documento.id, atual.ordem == sub.c.max_ordem),
        )

    consulta = consulta.where(atual.status.in_(status_visiveis(ctx)))

    linhas = ctx.db.execute(consulta).all()

    # (disciplina, fase, tipo) → nó, preservando a ordem dos catálogos.
    disciplinas: dict[str, NoDisciplina] = {}
    ordem_disc: dict[str, int] = {}
    fases_por_disc: dict[str, dict[str, NoFase]] = {}
    ordem_fase: dict[str, int] = {}
    tipos_por_fase: dict[tuple[str, str], dict[str, NoTipo]] = {}

    def somar(no, tamanho: int, data):
        no.tamanho += tamanho
        no.total += 1
        if no.atualizado_em is None or (data and data > no.atualizado_em):
            no.atualizado_em = data

    saida = ArvoreSaida(obra_codigo=ctx.obra.codigo, obra_nome=ctx.obra.nome)

    for arquivo, _revisao, _documento, disciplina, fase in linhas:
        d = disciplinas.get(disciplina.codigo)
        if d is None:
            d = NoDisciplina(
                chave=f"d:{disciplina.codigo}",
                codigo=disciplina.codigo,
                nome=disciplina.nome,
            )
            disciplinas[disciplina.codigo] = d
            ordem_disc[disciplina.codigo] = disciplina.ordem
            fases_por_disc[disciplina.codigo] = {}

        f = fases_por_disc[disciplina.codigo].get(fase.codigo)
        if f is None:
            f = NoFase(
                chave=f"d:{disciplina.codigo}|f:{fase.codigo}",
                codigo=fase.codigo,
                nome=fase.nome,
            )
            fases_por_disc[disciplina.codigo][fase.codigo] = f
            ordem_fase[fase.codigo] = fase.ordem
            tipos_por_fase[(disciplina.codigo, fase.codigo)] = {}

        chave_tipo = arquivo.tipo.value
        tp = tipos_por_fase[(disciplina.codigo, fase.codigo)].get(chave_tipo)
        if tp is None:
            tp = NoTipo(
                chave=f"d:{disciplina.codigo}|f:{fase.codigo}|t:{chave_tipo}",
                codigo=chave_tipo.upper(),
                nome=chave_tipo.upper(),
                tipo=arquivo.tipo,
            )
            tipos_por_fase[(disciplina.codigo, fase.codigo)][chave_tipo] = tp

        for no in (tp, f, d, saida):
            somar(no, arquivo.tamanho, arquivo.enviado_em)

    for (dcod, fcod), tipos in tipos_por_fase.items():
        fases_por_disc[dcod][fcod].tipos = sorted(
            tipos.values(), key=lambda x: ORDEM_TIPOS.get(x.tipo, 9)
        )

    for dcod, fases in fases_por_disc.items():
        disciplinas[dcod].fases = sorted(
            fases.values(), key=lambda x: (ordem_fase.get(x.codigo, 99), x.codigo)
        )

    saida.disciplinas = sorted(
        disciplinas.values(), key=lambda x: (ordem_disc.get(x.codigo, 99), x.codigo)
    )
    return saida


@router.get(
    "/obras/{obra_id}/pastas/{disciplina_codigo}/{fase_codigo}",
    response_model=PastaSaida,
)
def pasta(
    disciplina_codigo: str,
    fase_codigo: str,
    ctx: ContextoObra = Depends(contexto_obra),
):
    """Os documentos de uma disciplina numa fase, com o histórico inteiro.

    É o destino do clique na fase, dentro da árvore. Traz tudo de uma vez —
    documento, revisões e arquivos — porque a tela mostra tudo de uma vez, e
    N chamadas ao detalhe de documento seriam N viagens de rede.
    """
    disciplina = ctx.db.scalar(
        select(Disciplina).where(Disciplina.codigo == disciplina_codigo.upper())
    )
    fase = ctx.db.scalar(select(Fase).where(Fase.codigo == fase_codigo.upper()))
    if disciplina is None or fase is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pasta não encontrada.")

    documentos = list(
        ctx.db.scalars(
            select(Documento)
            .where(
                Documento.obra_id == ctx.obra.id,
                Documento.disciplina_id == disciplina.id,
                Documento.fase_id == fase.id,
            )
            # selectinload: sem isto seriam N+1 consultas por documento.
            .options(
                selectinload(Documento.revisoes).selectinload(Revisao.arquivos),
                selectinload(Documento.disciplina),
                selectinload(Documento.fase),
            )
            .order_by(Documento.codigo)
        )
    )

    saida: list[DocumentoDetalhe] = []
    for documento in documentos:
        revisoes = sorted(documento.revisoes, key=lambda r: r.ordem, reverse=True)
        visiveis = status_visiveis(ctx)
        revisoes = [r for r in revisoes if r.status in visiveis]
        if not revisoes:
            continue

        item = DocumentoDetalhe.model_validate(documento)
        item.total_revisoes = len(documento.revisoes)
        item.revisoes = [RevisaoOut.model_validate(r) for r in revisoes]
        atual = next(
            (r for r in revisoes if r.status != StatusRevisao.cancelado), None
        )
        item.revisao_atual = RevisaoResumo.model_validate(atual) if atual else None
        saida.append(item)

    return PastaSaida(
        obra_codigo=ctx.obra.codigo,
        obra_nome=ctx.obra.nome,
        disciplina=CatalogoResumo(codigo=disciplina.codigo, nome=disciplina.nome),
        fase=CatalogoResumo(codigo=fase.codigo, nome=fase.nome),
        total=len(saida),
        documentos=saida,
    )


@router.get("/documentos/{documento_id}", response_model=DocumentoDetalhe)
def detalhe(
    documento_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    ctx = montar_contexto(db, usuario, documento.obra_id)

    visiveis = status_visiveis(ctx)
    revisoes = sorted(documento.revisoes, key=lambda r: r.ordem, reverse=True)
    revisoes = [r for r in revisoes if r.status in visiveis]

    saida = DocumentoDetalhe.model_validate(documento)
    saida.total_revisoes = len(documento.revisoes)
    saida.revisoes = [RevisaoOut.model_validate(r) for r in revisoes]

    atual = next(
        (r for r in revisoes if r.status != StatusRevisao.cancelado), None
    )
    saida.revisao_atual = RevisaoResumo.model_validate(atual) if atual else None
    return saida


@router.patch("/documentos/{documento_id}", response_model=DocumentoOut)
def atualizar(
    documento_id: int,
    dados: DocumentoAtualizar,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    ctx = montar_contexto(db, usuario, documento.obra_id)
    ctx.exigir("enviar")

    if dados.titulo is not None:
        documento.titulo = dados.titulo.strip() or None

    auditoria.registrar(
        db, acao="documento_atualizado", entidade="documento",
        entidade_id=documento.id, usuario=usuario, obra_id=documento.obra_id,
        request=request,
    )
    db.commit()

    saida = DocumentoOut.model_validate(documento)
    saida.total_revisoes = len(documento.revisoes)
    return saida
