"""Logo do empreendimento: o que entra, quem troca e como ele é servido.

O logo aparece para todo mundo que abre a obra, então a porta de entrada dele
é estreita: só imagem de verdade (conferida pelos bytes, não pelo que o
navegador declara), só quem gerencia a obra, e servido de um jeito que o
navegador não consiga interpretar como outra coisa.
"""

from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from app.services.storage import armazenamento

from .conftest import autenticar

# PNG de 1×1 transparente, válido.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01"
    b"\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post(
        "/obras", json={"codigo": "MIL001", "nome": "Residencial Milos"}, headers=admin
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def projetista(cliente, admin, obra):
    r = cliente.post(
        "/usuarios",
        json={
            "nome": "Projetista Milos",
            "email": "projetista-milos@teste.com.br",
            "senha": "senha-projetista-2",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    add = cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": r.json()["id"], "papel": "projetista"},
        headers=admin,
    )
    assert add.status_code == 201, add.text
    return autenticar(cliente, "projetista-milos@teste.com.br", "senha-projetista-2")


def _enviar(cliente, cabecalhos, obra_id, dados, tipo="image/png"):
    return cliente.put(
        f"/obras/{obra_id}/logo",
        content=dados,
        headers={**cabecalhos, "Content-Type": tipo},
    )


def _logo_url(cliente, cabecalhos, obra_id):
    obras = cliente.get("/obras", headers=cabecalhos).json()
    return next(o for o in obras if o["id"] == obra_id)["logo_url"]


def _chave(url: str) -> str:
    return parse_qs(urlsplit(url).query)["chave"][0]


# --------------------------------------------------------------------------


def test_sem_logo_a_obra_vem_sem_endereco(cliente, admin, obra):
    assert _logo_url(cliente, admin, obra["id"]) is None


def test_png_vira_logo_servido_como_imagem(cliente, admin, obra):
    r = _enviar(cliente, admin, obra["id"], PNG)
    assert r.status_code == 200, r.text
    assert r.json()["logo_url"]

    url = _logo_url(cliente, admin, obra["id"])
    img = cliente.get(url)
    assert img.status_code == 200
    assert img.content == PNG
    assert img.headers["content-type"] == "image/png"
    # Exibir, não baixar — e sem o navegador adivinhar outro tipo.
    assert img.headers["content-disposition"] == "inline"
    assert img.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("dados,tipo", [(JPEG, "image/jpeg"), (WEBP, "image/webp")])
def test_jpeg_e_webp_tambem_servem(cliente, admin, obra, dados, tipo):
    assert _enviar(cliente, admin, obra["id"], dados, tipo).status_code == 200
    img = cliente.get(_logo_url(cliente, admin, obra["id"]))
    assert img.headers["content-type"] == tipo


def test_trocar_o_logo_apaga_o_antigo_e_muda_o_endereco(cliente, admin, obra):
    _enviar(cliente, admin, obra["id"], PNG)
    antigo = _logo_url(cliente, admin, obra["id"])

    _enviar(cliente, admin, obra["id"], PNG)
    novo = _logo_url(cliente, admin, obra["id"])

    # Endereço novo: nenhum navegador fica mostrando o logo anterior guardado.
    assert _chave(novo) != _chave(antigo)
    assert armazenamento.info(_chave(antigo)) == (False, 0)
    assert cliente.get(antigo).status_code == 404


@pytest.mark.parametrize(
    "dados,tipo",
    [
        # Declarar image/png não basta: quem manda são os bytes.
        (b"<html><script>alert(1)</script></html>", "image/png"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', "image/svg+xml"),
        (b"%PDF-1.7\n" + b"0" * 64, "application/pdf"),
    ],
)
def test_o_que_nao_e_imagem_e_recusado_e_o_logo_fica(cliente, admin, obra, dados, tipo):
    _enviar(cliente, admin, obra["id"], PNG)
    antes = _logo_url(cliente, admin, obra["id"])

    r = _enviar(cliente, admin, obra["id"], dados, tipo)
    assert r.status_code == 415
    assert _chave(_logo_url(cliente, admin, obra["id"])) == _chave(antes)


def test_logo_grande_demais_e_recusado(cliente, admin, obra):
    r = _enviar(cliente, admin, obra["id"], PNG + b"\x00" * (1024 * 1024))
    assert r.status_code == 413


def test_envio_vazio_e_recusado(cliente, admin, obra):
    assert _enviar(cliente, admin, obra["id"], b"").status_code == 400


def test_quem_nao_gerencia_a_obra_nao_troca_nem_remove(cliente, projetista, obra):
    assert _enviar(cliente, projetista, obra["id"], PNG).status_code == 403
    assert cliente.delete(f"/obras/{obra['id']}/logo", headers=projetista).status_code == 403


def test_quem_e_da_obra_ve_o_logo(cliente, admin, projetista, obra):
    _enviar(cliente, admin, obra["id"], PNG)
    url = _logo_url(cliente, projetista, obra["id"])
    assert cliente.get(url).content == PNG


def test_endereco_adulterado_e_recusado(cliente, admin, obra):
    _enviar(cliente, admin, obra["id"], PNG)
    partes = urlsplit(_logo_url(cliente, admin, obra["id"]))
    params = {k: v[0] for k, v in parse_qs(partes.query).items()}
    params["exp"] = str(int(params["exp"]) + 86400)  # esticar o prazo
    assert cliente.get(f"{partes.path}?{urlencode(params)}").status_code == 403


def test_link_de_imagem_nao_serve_para_baixar_arquivo(cliente, admin, obra):
    """A assinatura cobre a ação: um link de imagem não vira link de download
    (que serviria qualquer arquivo, sem conferir se é imagem)."""
    _enviar(cliente, admin, obra["id"], PNG)
    partes = urlsplit(_logo_url(cliente, admin, obra["id"]))
    params = {k: v[0] for k, v in parse_qs(partes.query).items()}
    params["acao"] = "get"
    assert cliente.get(f"{partes.path}?{urlencode(params)}").status_code == 403


def test_remover_o_logo(cliente, admin, obra):
    _enviar(cliente, admin, obra["id"], PNG)
    url = _logo_url(cliente, admin, obra["id"])

    r = cliente.delete(f"/obras/{obra['id']}/logo", headers=admin)
    assert r.status_code == 204
    assert _logo_url(cliente, admin, obra["id"]) is None
    assert cliente.get(url).status_code == 404
    # Remover de novo não é erro: o estado pedido já é o atual.
    assert cliente.delete(f"/obras/{obra['id']}/logo", headers=admin).status_code == 204


def test_troca_e_remocao_ficam_no_registro(cliente, admin, obra):
    _enviar(cliente, admin, obra["id"], PNG)
    cliente.delete(f"/obras/{obra['id']}/logo", headers=admin)
    eventos = cliente.get(f"/obras/{obra['id']}/eventos", headers=admin).json()
    itens = eventos["itens"] if isinstance(eventos, dict) else eventos
    acoes = {e["acao"] for e in itens}
    assert {"obra_logo_alterado", "obra_logo_removido"} <= acoes


# ------------------------------------------------------------ cor da obra


def test_cor_da_obra_define_e_limpa(cliente, admin, obra):
    r = cliente.patch(f"/obras/{obra['id']}", json={"cor": "#3A5B62"}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["cor"] == "#3a5b62"

    limpa = cliente.patch(f"/obras/{obra['id']}", json={"cor": ""}, headers=admin)
    assert limpa.json()["cor"] is None


def test_cor_fora_do_formato_e_recusada(cliente, admin, obra):
    """Vai direto para um atributo de estilo na tela: só #rrggbb passa."""
    for invalida in ["red", "#fff", "#12345g", "url(javascript:x)"]:
        r = cliente.patch(f"/obras/{obra['id']}", json={"cor": invalida}, headers=admin)
        assert r.status_code == 422, invalida
