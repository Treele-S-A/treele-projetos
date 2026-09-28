"""Entrada da Vercel.

A Vercel procura uma aplicação chamada `app` em arquivos como este, na raiz do
projeto, e a roda como uma função. O sistema de verdade mora em backend/app;
este arquivo só o põe ao alcance do import — sem mudar nada de como ele roda no
Docker, no Render ou na máquina de desenvolvimento.

A raiz do projeto na Vercel precisa ser a raiz do repositório, e não backend/:
o build compila a interface, que está em frontend/, e com a raiz em backend/ a
Vercel não deixa enxergar nada fora dela. Ver docs/vercel.md.
"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Padrões desta implantação, e não segredos — por isso aqui, e não no painel.
# Cada um que ficasse para o painel seria uma chance de esquecer, e o pior
# esquecimento não dá erro nenhum: sem DB_SCHEMA, as tabelas iriam parar no
# "public" do Supabase que outros sistemas da TREELE também usam. setdefault:
# uma variável definida no painel ainda vale mais que o padrão.
os.environ.setdefault("API_PREFIX", "/api")
os.environ.setdefault("ESTATICOS_DIR", str(RAIZ / "backend" / "estaticos"))
os.environ.setdefault("DB_SCHEMA", "treele")
# Na Vercel o disco é só leitura: arquivo nenhum pode ir para o modo local.
os.environ.setdefault("STORAGE_BACKEND", "s3")
# Produção de verdade, inclusive nas prévias: é o que liga a recusa de chave
# de sessão fraca (app/config.py).
os.environ.setdefault("AMBIENTE", "producao")

sys.path.insert(0, str(RAIZ / "backend"))

from app.main import app as _aplicacao  # noqa: E402

# Atribuição explícita: é o nome "app" neste arquivo que a Vercel procura.
app = _aplicacao
