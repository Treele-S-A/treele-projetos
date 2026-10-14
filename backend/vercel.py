"""Entrada FastAPI da Vercel Services.

O serviço backend tem raiz em ``backend/``; este módulo aplica os padrões de
produção que antes eram definidos pelo ``index.py`` da raiz do repositório.
Segredos e credenciais continuam vindo das variáveis de ambiente da Vercel.
"""

import os

os.environ.setdefault("API_PREFIX", "/api")
os.environ.setdefault("DB_SCHEMA", "treele")
os.environ.setdefault("STORAGE_BACKEND", "s3")
os.environ.setdefault("AMBIENTE", "producao")

from app.main import app  # noqa: E402
