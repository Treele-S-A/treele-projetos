"""Visualizador 3D de IFC (TREELE, 21/10/2026): a rota do modelo segue a regra
do download, entrega o IFC para converter na primeira vez e o modelo leve
depois que alguém da equipe guardou a conversão."""

from urllib.parse import urlsplit

import pytest

from app.services.storage import armazenamento

from .conftest import autenticar, enviar_arquivo

SENHA = "senha-mod3d-12345"
IFC = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n" + b" " * 300
FRAG = b"\x00fragments" * 50
PDF = b"%PDF-1.7\n" + b"0" * 200


def _pessoa(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@mod3d.teste.com.br"
    u = cliente.post("/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA},
                     headers=admin).json()
    cliente.post(f"/obras/{obra['id']}/membros", json={"usuario_id": u["id"], "papel": papel}, headers=admin)
    return autenticar(cliente, email, SENHA)


@pytest.fixture(scope="module")
def c(cliente, admin):
    obra = cliente.post("/obras", json={"codigo": "M3D", "nome": "Obra 3D", "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"}, headers=admin).json()
    coord = _pessoa(cliente, admin, obra, "coordm3d", "coordenador")
    campo = _pessoa(cliente, admin, obra, "campom3d", "obra")
    ids = {}
    for nome, conteudo, liberar in (("M3D-ARQ-PE-MOD-R00.ifc", IFC, True), ("M3D-ARQ-PE-MOD-R00.pdf", PDF, True),
                                    ("M3D-HID-PE-MOD-R00.ifc", IFC, False)):
        r = enviar_arquivo(cliente, coord, obra["id"], nome, conteudo)
        assert r.status_code == 200, r.text
        ids[nome] = r.json()["arquivo"]["id"]
        if liberar and nome.endswith(".pdf"):
            p = cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={"avisar": False}, headers=coord)
            assert p.status_code == 200, p.text
    return {"obra": obra, "coord": coord, "campo": campo, **ids}


def _modelo(cliente, cab, arquivo_id):
    return cliente.get(f"/arquivos/{arquivo_id}/modelo", headers=cab)


def test_primeira_abertura_entrega_o_ifc_e_o_envio_da_conversao(cliente, c):
    r = _modelo(cliente, c["coord"], c["M3D-HID-PE-MOD-R00.ifc"])
    assert r.status_code == 200, r.text
    m = r.json()
    assert (m["documento"], m["disciplina"], m["revisao"]) == ("M3D-HID-PE-MOD", "HID", "00")
    assert m["modelo_url"] is None and m["ifc_url"] and m["envio"]["metodo"] == "PUT"
    assert "EM REVISÃO" in m["aviso"]


def test_conversao_guardada_abre_o_modelo_leve(cliente, c):
    arquivo_id = c["M3D-ARQ-PE-MOD-R00.ifc"]
    envio = _modelo(cliente, c["coord"], arquivo_id).json()["envio"]
    partes = urlsplit(envio["url"])
    assert cliente.put(f"{partes.path}?{partes.query}", content=FRAG).status_code == 200
    m = _modelo(cliente, c["coord"], arquivo_id).json()
    assert m["modelo_url"] and m["tamanho_modelo"] == len(FRAG)
    assert m["ifc_url"] is None and m["envio"] is None
    # O modelo leve é baixado como qualquer arquivo assinado.
    partes = urlsplit(m["modelo_url"])
    assert cliente.get(f"{partes.path}?{partes.query}").content == FRAG


def test_obra_abre_o_liberado_mas_nao_guarda_conversao(cliente, c):
    # A obra vê a ARQ liberada (o PDF liberou a revisão inteira).
    arquivo_id = c["M3D-ARQ-PE-MOD-R00.ifc"]
    armazenamento.remover(f"{_chave(cliente, c, arquivo_id)}")
    m = _modelo(cliente, c["campo"], arquivo_id).json()
    assert m["ifc_url"] and m["envio"] is None
    # Em análise, a obra não abre — a mesma resposta do download avulso.
    r = _modelo(cliente, c["campo"], c["M3D-HID-PE-MOD-R00.ifc"])
    assert r.status_code == 403 and "não foi liberada" in r.json()["detail"]


def test_so_ifc_abre_no_visualizador(cliente, c):
    r = _modelo(cliente, c["coord"], c["M3D-ARQ-PE-MOD-R00.pdf"])
    assert r.status_code == 415


def test_abertura_fica_no_registro(cliente, admin, c):
    _modelo(cliente, c["coord"], c["M3D-ARQ-PE-MOD-R00.ifc"])
    eventos = cliente.get(f"/obras/{c['obra']['id']}/eventos?acao=visualizacao", headers=admin).json()
    itens = eventos["itens"] if isinstance(eventos, dict) else eventos
    assert any((e.get("detalhes") or {}).get("arquivo") == "M3D-ARQ-PE-MOD-R00.ifc" for e in itens)


def test_excluir_ifc_em_analise_leva_o_modelo_junto(cliente, admin, c):
    arquivo_id = c["M3D-HID-PE-MOD-R00.ifc"]
    envio = _modelo(cliente, c["coord"], arquivo_id).json()["envio"]
    partes = urlsplit(envio["url"])
    cliente.put(f"{partes.path}?{partes.query}", content=FRAG)
    chave = _chave(cliente, c, arquivo_id)
    assert armazenamento.info(chave)[0]
    assert cliente.delete(f"/arquivos/{arquivo_id}", headers=admin).status_code == 204
    assert not armazenamento.info(chave)[0]


def _chave(cliente, c, arquivo_id):
    from app.api.arquivos import chave_modelo
    from app.db import SessionLocal
    from app.models import Arquivo

    db = SessionLocal()
    try:
        return chave_modelo(db.get(Arquivo, arquivo_id))
    finally:
        db.close()
