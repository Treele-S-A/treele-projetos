"""Arquivos de implantação que precisam andar juntos com o código.

Nada aqui roda em produção — mas um erro nestes arquivos só aparece na hora do
deploy, longe de quem mudou o código. Melhor falhar no teste.
"""

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _dependencias(caminho: Path) -> list[str]:
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in linhas if l.strip() and not l.strip().startswith("#")]


def test_dependencias_da_vercel_iguais_as_do_backend():
    """A Vercel lê requirements.txt na raiz; Docker e desenvolvimento, o de
    backend/. Dependência nova num só deles subiria sem ela no outro."""
    assert _dependencias(RAIZ / "requirements.txt") == _dependencias(
        RAIZ / "backend" / "requirements.txt"
    )


def test_vercel_compila_a_interface_apontando_para_a_api_na_mesma_origem():
    config = json.loads((RAIZ / "vercel.json").read_text(encoding="utf-8"))
    # Sem isto a interface compilada procuraria a API em localhost:8000.
    assert "VITE_API=/api" in config["buildCommand"]
    # A função é o index.py da raiz — o mesmo arquivo que a Vercel executa.
    assert "index.py" in config["functions"]
    assert (RAIZ / "index.py").is_file()


def test_entrada_da_vercel_entrega_a_aplicacao():
    """O index.py da raiz tem que expor a mesma aplicação de backend/app."""
    import runpy

    from app.main import app as esperado

    modulo = runpy.run_path(str(RAIZ / "index.py"))
    assert modulo["app"] is esperado


def test_pagina_inicial_nunca_fica_guardada_no_navegador(tmp_path):
    """Caso real (01/10/2026): depois de uma atualização, tela em branco.

    Na Vercel a data dos arquivos é zerada e o index tem sempre o mesmo
    tamanho, então ETag e Last-Modified não mudavam entre versões. O navegador
    revalidava, recebia 304 e ficava com o index antigo — que apontava para um
    JS que a versão nova já não tinha."""
    from app.main import pagina_inicial

    index = tmp_path / "index.html"
    index.write_text("<!doctype html><script src=/assets/index-abc.js></script>")

    r = pagina_inicial(index)

    assert r.headers["cache-control"] == "no-store"
    assert "etag" not in r.headers
    assert "last-modified" not in r.headers
    assert b"index-abc.js" in r.body
