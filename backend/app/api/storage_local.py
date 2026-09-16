"""Endpoint que emula URLs pré-assinadas no back-end ``local``.

Existe para o sistema rodar sem Docker/MinIO durante o desenvolvimento. Em
produção (``STORAGE_BACKEND=s3``) estas rotas simplesmente não são usadas: o
navegador fala direto com o storage.

A autorização aqui é a própria assinatura HMAC da URL, não o token de sessão —
é assim que um `PUT` direto do navegador funciona sem cabeçalho extra.
"""

import hashlib
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, Response

from ..config import settings
from ..services.storage import ArmazenamentoLocal, armazenamento

router = APIRouter(prefix="/storage", tags=["storage"], include_in_schema=False)


def _validar(chave: str, acao: str, exp: int, assinatura: str) -> ArmazenamentoLocal:
    if not isinstance(armazenamento, ArmazenamentoLocal):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Back-end de armazenamento não é local."
        )
    if not armazenamento.conferir_assinatura(chave, acao, exp, assinatura):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Link expirado ou inválido. Recarregue a página."
        )
    return armazenamento


@router.put("/local")
async def enviar(request: Request, chave: str, acao: str, exp: int, assinatura: str):
    if acao != "put":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ação inválida para este link.")
    local = _validar(chave, acao, exp, assinatura)

    try:
        caminho = local.caminho(chave)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chave inválida.")

    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".parcial")

    digest = hashlib.sha256()
    tamanho = 0
    try:
        with open(temporario, "wb") as fh:
            async for pedaco in request.stream():
                if not pedaco:
                    continue
                tamanho += len(pedaco)
                if tamanho > settings.tamanho_max_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"Arquivo excede o limite de {settings.tamanho_max_mb} MB.",
                    )
                digest.update(pedaco)
                fh.write(pedaco)
    except Exception:
        temporario.unlink(missing_ok=True)
        raise

    temporario.replace(caminho)
    return Response(status_code=status.HTTP_200_OK, headers={"ETag": digest.hexdigest()})


@router.get("/local")
def baixar(chave: str, acao: str, exp: int, assinatura: str, nome: str | None = None):
    if acao != "get":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ação inválida para este link.")
    local = _validar(chave, acao, exp, assinatura)

    try:
        caminho = local.caminho(chave)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chave inválida.")

    if not caminho.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo não encontrado.")

    nome_final = nome or caminho.name
    return FileResponse(
        caminho,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome_final)}"
        },
    )
