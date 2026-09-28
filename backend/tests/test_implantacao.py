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
