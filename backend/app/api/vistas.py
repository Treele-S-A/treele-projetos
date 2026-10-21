"""Vistas do modelo 3D (TREELE, 21/10/2026).

Uma vista é o retrato de uma cena do visualizador: os modelos, a câmera, os
cortes, os elementos selecionados e a imagem da tela com as marcações. Ela
nasce no visualizador e acompanha o pedido de correção (a solicitação de
revisão aponta para ela, e a imagem vai como anexo); quem recebe o pedido
reabre a cena exatamente como estava.

A imagem sobe direto do navegador para o armazenamento, como os anexos.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import montar_contexto, usuario_atual
from ..enums import TipoArquivo
from ..models import Arquivo, Usuario, VistaModelo
from ..schemas import EnvioModelo, ModeloDaVista, UsuarioOut, VistaCriada, VistaCriar, VistaOut
from ..services import auditoria
from ..services.storage import _ascii_seguro, armazenamento

router = APIRouter(tags=["vistas"])

IMAGEM_MAX_MB = 15


def chave_imagem(obra_codigo: str) -> str:
    return f"obras/{_ascii_seguro(obra_codigo)}/_vistas/{secrets.token_hex(8)}.png"


def saida(db: Session, vista: VistaModelo) -> VistaOut:
    modelos = []
    for arquivo_id in vista.arquivos:
        a = db.get(Arquivo, arquivo_id)
        if a is None:
            continue
        doc = a.revisao.documento
        modelos.append(ModeloDaVista(
            arquivo_id=a.id, documento=doc.codigo, documento_id=doc.id,
            revisao=a.revisao.numero, disciplina=doc.disciplina.codigo,
        ))
    return VistaOut(
        id=vista.id, obra_id=vista.obra_id, titulo=vista.titulo, arquivos=vista.arquivos,
        camera=vista.camera, cortes=vista.cortes, selecao=vista.selecao, ocultos=vista.ocultos,
        modelos=modelos,
        imagem_url=(
            armazenamento.url_imagem(vista.imagem_key, "image/png") if vista.imagem_tamanho else None
        ),
        criada_por=UsuarioOut.model_validate(vista.criada_por) if vista.criada_por else None,
        criada_em=vista.criada_em,
    )


def _vista(db: Session, usuario: Usuario, vista_id: int) -> VistaModelo:
    vista = db.get(VistaModelo, vista_id)
    if vista is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vista não encontrada.")
    montar_contexto(db, usuario, vista.obra_id)  # quem não é da obra não vê
    return vista


@router.post("/obras/{obra_id}/vistas", response_model=VistaCriada, status_code=status.HTTP_201_CREATED)
def criar(
    obra_id: int,
    dados: VistaCriar,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    from .arquivos import _conferir_leitura

    ctx = montar_contexto(db, usuario, obra_id)
    arquivos = list(dict.fromkeys(dados.arquivos))
    for arquivo_id in arquivos:
        a = db.get(Arquivo, arquivo_id)
        if (
            a is None
            or a.tipo != TipoArquivo.ifc
            or a.revisao.documento.obra_id != obra_id
            or not ctx.ve_disciplina(a.revisao.documento.disciplina.codigo)
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Modelo {arquivo_id} não é desta obra.")
        _conferir_leitura(a, ctx)  # a vista só leva o que a pessoa pode abrir
    vista = VistaModelo(
        obra_id=obra_id,
        titulo=dados.titulo.strip(),
        arquivos=arquivos,
        camera=dados.camera.model_dump(),
        cortes=[c.model_dump() for c in dados.cortes],
        selecao={k: v[:500] for k, v in dados.selecao.items() if k.isdigit() and int(k) in arquivos},
        ocultos=[i for i in dados.ocultos if i in arquivos],
        imagem_key=chave_imagem(ctx.obra.codigo),
        criada_por_id=usuario.id,
    )
    db.add(vista)
    db.flush()
    destino = armazenamento.destino_upload(vista.imagem_key, "image/png")
    auditoria.registrar(
        db, acao="vista_criada", entidade="vista", entidade_id=vista.id,
        usuario=usuario, obra_id=obra_id, detalhes={"titulo": vista.titulo, "arquivos": arquivos},
        request=request,
    )
    db.commit()
    db.refresh(vista)
    return VistaCriada(
        vista=saida(db, vista),
        envio_imagem=EnvioModelo(url=destino.url, metodo=destino.metodo, headers=destino.headers),
    )


@router.post("/vistas/{vista_id}/imagem", response_model=VistaOut)
def confirmar_imagem(
    vista_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Confere que a imagem chegou ao armazenamento."""
    vista = _vista(db, usuario, vista_id)
    if vista.criada_por_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vista não encontrada.")
    existe, tamanho = armazenamento.info(vista.imagem_key)
    if not existe or not tamanho:
        raise HTTPException(status.HTTP_409_CONFLICT, "A imagem da vista não chegou. Tente de novo.")
    if tamanho > IMAGEM_MAX_MB * 1024 * 1024:
        armazenamento.remover(vista.imagem_key)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Imagem da vista grande demais.")
    vista.imagem_tamanho = tamanho
    db.commit()
    return saida(db, vista)


@router.get("/vistas/{vista_id}", response_model=VistaOut)
def detalhe(vista_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return saida(db, _vista(db, usuario, vista_id))


@router.get("/obras/{obra_id}/vistas", response_model=list[VistaOut])
def listar(obra_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    montar_contexto(db, usuario, obra_id)
    vistas = db.scalars(
        select(VistaModelo)
        .where(VistaModelo.obra_id == obra_id, VistaModelo.imagem_tamanho > 0)
        .order_by(VistaModelo.criada_em.desc())
        .limit(100)
    )
    return [saida(db, v) for v in vistas]
