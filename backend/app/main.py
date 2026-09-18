"""Ponto de entrada da API.

    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from .db import SessionLocal, engine
from .migracoes import aplicar as aplicar_migracoes
from .seed import semear
from .services.storage import ArmazenamentoS3, armazenamento


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    aplicar_migracoes(engine)
    with SessionLocal() as db:
        semear(db)
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
    root_path=settings.root_path,
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
    app.include_router(modulo.router)


@app.get("/saude", tags=["infra"])
def saude():
    return {
        "ok": True,
        "ambiente": settings.ambiente,
        "storage": settings.storage_backend,
    }
