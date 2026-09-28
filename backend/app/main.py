"""Ponto de entrada da API.

    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import (
    arquivos,
    auth,
    catalogos,
    documentos,
    eventos,
    obras,
    revisoes,
    storage_local,
    uploads,
    usuarios,
)
from .config import settings
from .db import engine
from .migracoes import preparar_banco
from .services.storage import ArmazenamentoS3, armazenamento


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    preparar_banco(engine)
    if isinstance(armazenamento, ArmazenamentoS3):
        armazenamento.garantir_bucket()
    yield


app = FastAPI(
    title=settings.app_nome,
    version="1.0.0",
    description=(
        "Controle de revisões de projetos. Fase 1: nomenclatura padronizada, "
        "catálogo por obra/disciplina/fase/tipo, status e trilha de auditoria."
    ),
    lifespan=ciclo_de_vida,
    # A documentação acompanha o prefixo. Sem isto ela ficaria na raiz, junto
    # com as telas, descrevendo rotas que moram em outro lugar.
    docs_url=settings.api_prefix + "/docs",
    redoc_url=settings.api_prefix + "/redoc",
    openapi_url=settings.api_prefix + "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.lista_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "ETag"],
)

for modulo in (
    auth,
    usuarios,
    catalogos,
    obras,
    documentos,
    uploads,
    revisoes,
    arquivos,
    eventos,
    storage_local,
):
    app.include_router(modulo.router, prefix=settings.api_prefix)


@app.get(settings.api_prefix + "/saude", tags=["infra"])
def saude():
    return {
        "ok": True,
        "ambiente": settings.ambiente,
        "storage": settings.storage_backend,
    }


# --------------------------------------------------------------------------
# Interface, quando ela vem junto
# --------------------------------------------------------------------------
#
# Num contêiner só, a mesma aplicação serve a API sob /api e as telas sob /.
# Poupa um serviço na hospedagem e elimina o CORS: mesma origem, sem endereço
# de API para configurar em lugar nenhum.

if settings.estaticos_dir and settings.estaticos_dir.is_dir():
    ESTATICOS = settings.estaticos_dir
    INDEX = ESTATICOS / "index.html"

    # Os arquivos com hash no nome podem ser guardados para sempre pelo
    # navegador; o index.html, nunca.
    app.mount(
        "/assets", StaticFiles(directory=ESTATICOS / "assets"), name="assets"
    )

    @app.get("/{caminho:path}", include_in_schema=False)
    def interface(caminho: str):
        """Devolve o arquivo pedido ou o index.html.

        O index para qualquer rota desconhecida é o que faz recarregar a página
        em /obras/1/acervo funcionar: quem resolve a rota é o React, no
        navegador, e para isso ele precisa ser carregado primeiro.
        """
        if caminho.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Rota de API inexistente.")

        arquivo = (ESTATICOS / caminho).resolve()
        if ESTATICOS.resolve() in arquivo.parents and arquivo.is_file():
            return FileResponse(arquivo)
        return FileResponse(INDEX)
