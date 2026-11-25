"""Atas de mudança de projeto (TREELE, 25/11/2026): PDFs por obra e
disciplina, numerados na ordem em que chegam (SER-HID-AMP01-R00), com
revisões e exclusão. Só dos coordenadores da obra."""

from urllib.parse import urlsplit

from .conftest import autenticar

SENHA = "senha-amp-12345"
PDF = b"%PDF-1.7\n" + b"0" * 300
CASA = "Rua de Teste, 100 – Centro – Curitiba – PR"


def _pessoa(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@amp.teste.com.br"
    u = cliente.post("/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA}, headers=admin).json()
    cliente.post(f"/obras/{obra}/membros", json={"usuario_id": u["id"], "papel": papel}, headers=admin)
    return autenticar(cliente, email, SENHA)


def _disciplina(cliente, cab, codigo):
    return next(d["id"] for d in cliente.get("/disciplinas", headers=cab).json() if d["codigo"] == codigo)


def _enviar(cliente, cab, obra, nome, **corpo):
    r = cliente.post(f"/obras/{obra}/atas-mudanca/envios", json={"nome_arquivo": nome, "tamanho": len(PDF), **corpo},
                     headers=cab)
    assert r.status_code == 201, r.text
    partes = urlsplit(r.json()["url"])
    assert cliente.put(f"{partes.path}?{partes.query}", content=PDF).status_code == 200
    c = cliente.post(f"/atas-mudanca/envios/{r.json()['envio_id']}/confirmar", headers=cab)
    assert c.status_code == 200, c.text
    return c.json()


def test_numera_na_ordem_com_revisoes_e_exclusao(cliente, admin):
    ser = cliente.post("/obras", json={"codigo": "SRA", "nome": "Obra AMP", "endereco": CASA}, headers=admin).json()["id"]
    mil = cliente.post("/obras", json={"codigo": "MLA", "nome": "Outra AMP", "endereco": CASA}, headers=admin).json()["id"]
    coord = _pessoa(cliente, admin, ser, "coordamp", "coordenador")
    hid, arq = _disciplina(cliente, coord, "HID"), _disciplina(cliente, coord, "ARQ")

    a1 = _enviar(cliente, coord, ser, "ata reunião 12-11.pdf", disciplina_id=hid, assunto="Troca do PEX por PPR")
    assert a1["codigo"] == "SRA-HID-AMP01" and [r["codigo"] for r in a1["revisoes"]] == ["SRA-HID-AMP01-R00"]
    assert a1["assunto"] == "Troca do PEX por PPR"
    r1 = _enviar(cliente, coord, ser, "qualquer nome.PDF", ata_id=a1["id"])
    assert [r["codigo"] for r in r1["revisoes"]] == ["SRA-HID-AMP01-R00", "SRA-HID-AMP01-R01"]
    a2 = _enviar(cliente, coord, ser, "outra.pdf", disciplina_id=hid)
    assert a2["codigo"] == "SRA-HID-AMP02"
    assert _enviar(cliente, coord, ser, "arq.pdf", disciplina_id=arq)["codigo"] == "SRA-ARQ-AMP01"
    assert _enviar(cliente, admin, mil, "mil.pdf", disciplina_id=arq)["revisoes"][0]["codigo"] == "MLA-ARQ-AMP01-R00"

    lista = cliente.get(f"/obras/{ser}/atas-mudanca", headers=coord).json()
    assert {a["codigo"] for a in lista} == {"SRA-HID-AMP01", "SRA-HID-AMP02", "SRA-ARQ-AMP01"}
    # O PDF baixa com o nome do sistema.
    rev = r1["revisoes"][1]
    v = cliente.get(f"/atas-mudanca/revisoes/{rev['id']}/visualizar?baixar=true", headers=coord).json()
    assert v["nome"] == "SRA-HID-AMP01-R01.pdf"
    partes = urlsplit(v["url"])
    assert cliente.get(f"{partes.path}?{partes.query}").content == PDF

    # Só PDF; disciplina obrigatória na ata nova.
    assert cliente.post(f"/obras/{ser}/atas-mudanca/envios", json={"nome_arquivo": "x.docx", "tamanho": 10, "disciplina_id": hid},
                        headers=coord).status_code == 415
    assert cliente.post(f"/obras/{ser}/atas-mudanca/envios", json={"nome_arquivo": "x.pdf", "tamanho": 10},
                        headers=coord).status_code == 422

    # Excluir a R01: a próxima revisão volta a ser R01. Excluir a única
    # revisão leva a ata junto.
    assert cliente.delete(f"/atas-mudanca/revisoes/{rev['id']}", headers=coord).status_code == 204
    assert [r["codigo"] for r in _enviar(cliente, coord, ser, "nova.pdf", ata_id=a1["id"])["revisoes"]][-1] == "SRA-HID-AMP01-R01"
    assert cliente.delete(f"/atas-mudanca/revisoes/{a2['revisoes'][0]['id']}", headers=coord).status_code == 204
    assert "SRA-HID-AMP02" not in {a["codigo"] for a in cliente.get(f"/obras/{ser}/atas-mudanca", headers=coord).json()}
    # A ata inteira.
    assert cliente.delete(f"/atas-mudanca/{a1['id']}", headers=coord).status_code == 204
    assert {a["codigo"] for a in cliente.get(f"/obras/{ser}/atas-mudanca", headers=coord).json()} == {"SRA-ARQ-AMP01"}

    obras = {o["codigo"]: o["atas"] for o in cliente.get("/atas-mudanca/obras", headers=coord).json()}
    assert obras == {"SRA": 1}  # só as que ele coordena


def test_so_coordenador(cliente, admin):
    obra = cliente.post("/obras", json={"codigo": "SRB", "nome": "Obra AMP B", "endereco": CASA}, headers=admin).json()["id"]
    hid = _disciplina(cliente, admin, "HID")
    ata = _enviar(cliente, admin, obra, "a.pdf", disciplina_id=hid)
    for apelido, papel in (("projamp", "projetista"), ("campoamp", "obra")):
        cab = _pessoa(cliente, admin, obra, apelido, papel)
        assert cliente.get(f"/obras/{obra}/atas-mudanca", headers=cab).status_code == 403
        assert cliente.post(f"/obras/{obra}/atas-mudanca/envios", json={"nome_arquivo": "a.pdf", "tamanho": 10, "disciplina_id": hid},
                            headers=cab).status_code == 403
        assert cliente.delete(f"/atas-mudanca/{ata['id']}", headers=cab).status_code == 403
        assert cliente.get("/atas-mudanca/obras", headers=cab).json() == []
