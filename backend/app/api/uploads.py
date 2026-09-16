"""Fluxo de envio de arquivo.

Três passos, e o arquivo nunca passa pela API:

1. ``POST /obras/{id}/uploads/iniciar`` — valida a nomenclatura, cria/acha o
   documento e a revisão, devolve uma URL assinada.
2. O navegador envia os bytes direto para essa URL.
3. ``POST /arquivos/{id}/confirmar`` — a API confere que o objeto chegou.

Se o passo 2 ou 3 falhar, a linha do arquivo fica em ``pendente`` e não conta
para nada: não aparece para a obra e não satisfaz a regra de companheiro.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from ..config import settings
from ..deps import (
    ContextoObra,
    codigos_disciplinas,
    codigos_fases,
    contexto_obra,
    padrao_da_obra,
)
from ..enums import StatusArquivo, StatusRevisao, TipoArquivo
from ..models import Disciplina, Documento, Fase, Revisao, Arquivo
from ..schemas import UploadIniciarEntrada, UploadIniciarSaida
from ..services import auditoria
from ..services.nomenclatura import analisar
from ..services.storage import armazenamento, montar_chave

router = APIRouter(tags=["envio"])

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "dwg": "image/vnd.dwg",
    "rvt": "application/octet-stream",
    "ifc": "application/x-step",
}


@router.post(
    "/obras/{obra_id}/uploads/iniciar",
    response_model=UploadIniciarSaida,
    status_code=status.HTTP_201_CREATED,
)
def iniciar(
    dados: UploadIniciarEntrada,
    request: Request,
    ctx: ContextoObra = Depends(contexto_obra),
):
    ctx.exigir("enviar", "Seu papel nesta obra não permite enviar arquivos.")
    db = ctx.db

    if dados.tamanho > settings.tamanho_max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Arquivo de {dados.tamanho / 1048576:.0f} MB excede o limite de "
            f"{settings.tamanho_max_mb} MB.",
        )

    padrao = padrao_da_obra(db, ctx.obra.id)
    r = analisar(
        dados.nome_arquivo,
        padrao.template,
        padrao.tokens,
        padrao.extensoes,
        obra_codigo=ctx.obra.codigo,
        disciplinas=codigos_disciplinas(db),
        fases=codigos_fases(db),
    )
    if not r.valido:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "mensagem": "O nome do arquivo não segue o padrão da obra.",
                "erros": r.erros,
                "esperado": padrao.template,
                "exemplo": padrao.exemplo,
            },
        )

    disciplina = db.scalar(
        select(Disciplina).where(Disciplina.codigo == r.disciplina_codigo)
    )
    fase = db.scalar(select(Fase).where(Fase.codigo == r.fase_codigo))
    if disciplina is None or fase is None:  # pragma: no cover - já validado acima
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Disciplina ou fase do nome do arquivo não está cadastrada.",
        )

    # --- documento --------------------------------------------------------
    documento = db.scalar(
        select(Documento).where(
            Documento.obra_id == ctx.obra.id, Documento.codigo == r.codigo_documento
        )
    )
    documento_novo = documento is None
    if documento is None:
        documento = Documento(
            obra_id=ctx.obra.id,
            disciplina_id=disciplina.id,
            fase_id=fase.id,
            codigo=r.codigo_documento,
            titulo=r.titulo,
            criado_por_id=ctx.usuario.id,
        )
        db.add(documento)
        db.flush()
    elif r.titulo and not documento.titulo:
        documento.titulo = r.titulo

    # --- revisão ----------------------------------------------------------
    revisao = db.scalar(
        select(Revisao).where(
            Revisao.documento_id == documento.id, Revisao.numero == r.revisao_numero
        )
    )
    revisao_nova = revisao is None
    if revisao is None:
        revisao = Revisao(
            documento_id=documento.id,
            numero=r.revisao_numero,
            ordem=r.revisao_ordem,
            status=StatusRevisao.em_revisao,
            descricao=dados.descricao,
            criada_por_id=ctx.usuario.id,
        )
        db.add(revisao)
        db.flush()
    elif revisao.status != StatusRevisao.em_revisao:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A revisão R{revisao.numero} de {documento.codigo} está fechada "
            f"({revisao.status.rotulo}) e não aceita mais arquivos. "
            "Envie uma revisão nova.",
        )
    elif dados.descricao and not revisao.descricao:
        revisao.descricao = dados.descricao

    # --- arquivo ----------------------------------------------------------
    tipo = TipoArquivo.da_extensao(dados.nome_arquivo)
    existente = db.scalar(
        select(Arquivo).where(
            Arquivo.revisao_id == revisao.id,
            Arquivo.nome_original == dados.nome_arquivo,
        )
    )
    if existente is not None and not dados.substituir:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"'{dados.nome_arquivo}' já existe na revisão R{revisao.numero}. "
            "Reenvie marcando a opção de substituir se quiser trocá-lo.",
        )

    chave = montar_chave(
        ctx.obra.codigo, documento.codigo, revisao.numero, dados.nome_arquivo
    )
    content_type = CONTENT_TYPES.get(r.extensao or "", dados.content_type)

    if existente is not None:
        if existente.storage_key != chave:
            armazenamento.remover(existente.storage_key)
        arquivo = existente
        arquivo.status = StatusArquivo.pendente
        arquivo.tamanho = 0
        arquivo.sha256 = None
        arquivo.storage_key = chave
        arquivo.content_type = content_type
        arquivo.enviado_por_id = ctx.usuario.id
    else:
        arquivo = Arquivo(
            revisao_id=revisao.id,
            nome_original=dados.nome_arquivo,
            tipo=tipo,
            status=StatusArquivo.pendente,
            storage_key=chave,
            content_type=content_type,
            tamanho=0,
            enviado_por_id=ctx.usuario.id,
        )
        db.add(arquivo)
    db.flush()

    destino = armazenamento.destino_upload(chave, content_type)

    auditoria.registrar(
        db, acao="upload_iniciado", entidade="arquivo", entidade_id=arquivo.id,
        usuario=ctx.usuario, obra_id=ctx.obra.id,
        detalhes={
            "documento": documento.codigo,
            "revisao": revisao.numero,
            "arquivo": dados.nome_arquivo,
        },
        request=request,
    )
    db.commit()

    return UploadIniciarSaida(
        arquivo_id=arquivo.id,
        revisao_id=revisao.id,
        documento_id=documento.id,
        url=destino.url,
        metodo=destino.metodo,
        headers=destino.headers,
        direto=destino.direto,
        revisao_nova=revisao_nova,
        documento_novo=documento_novo,
    )
