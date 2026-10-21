"""Download em lote (TREELE, 21/10/2026): a lista de arquivos das revisões
marcadas segue a regra do download avulso, e o download de cada arquivo é o
avulso, que registra quem baixou."""

import pytest

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
DWG = b"AC1032" + b"\x00" * 200
SENHA = "senha-dlote-12345"
OBRA = "DLT"


def _usuario(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@dlote.teste.com.br"
    r = cliente.post("/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA}, headers=admin)
    assert r.status_code == 201, r.text
    m = cliente.post(f"/obras/{obra['id']}/membros", json={"usuario_id": r.json()["id"], "papel": papel},
                     headers=admin)
    assert m.status_code in (200, 201), m.text
    return autenticar(cliente, email, SENHA)


def _enviar(cliente, cab, nome, conteudo):
    r = enviar_arquivo(cliente, cab, cenario_obra["id"], nome, conteudo)
    assert r.status_code == 200, r.text
    return r.json()["revisao"]


cenario_obra: dict = {}


@pytest.fixture(scope="module")
def c(cliente, admin):
    obra = cliente.post("/obras", json={"codigo": OBRA, "nome": "Obra download"}, headers=admin).json()
    cenario_obra.update(obra)
    pessoas = {
        "coord": _usuario(cliente, admin, obra, "coorddlt", "coordenador"),
        "campo": _usuario(cliente, admin, obra, "campodlt", "obra"),
    }
    # Liberada com PDF e DWG; outra só em revisão.
    liberada = _enviar(cliente, pessoas["coord"], f"{OBRA}-ARQ-PE-001-R00.pdf", PDF)
    _enviar(cliente, pessoas["coord"], f"{OBRA}-ARQ-PE-001-R00.dwg", DWG)
    r = cliente.post(f"/revisoes/{liberada['id']}/publicar", json={"avisar": False}, headers=pessoas["coord"])
    assert r.status_code == 200, r.text
    em_revisao = _enviar(cliente, pessoas["coord"], f"{OBRA}-EST-PE-001-R00.pdf", PDF)
    return {"obra": obra, **pessoas, "liberada": liberada["id"], "em_revisao": em_revisao["id"]}


def _lote(cliente, cab, ids):
    r = cliente.post("/revisoes/arquivos-lote", json={"revisao_ids": ids}, headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def test_coordenador_recebe_todos_os_arquivos_com_pasta_e_aviso(cliente, c):
    r = _lote(cliente, c["coord"], [c["liberada"], c["em_revisao"], c["liberada"]])
    nomes = [(a["nome"], a["tipo"], a["pasta"]) for a in r["arquivos"]]
    assert nomes == [
        (f"{OBRA}-ARQ-PE-001-R00.dwg", "dwg", f"{OBRA}/ARQ"),
        (f"{OBRA}-ARQ-PE-001-R00.pdf", "pdf", f"{OBRA}/ARQ"),
        (f"{OBRA}-EST-PE-001-R00.pdf", "pdf", f"{OBRA}/EST"),
    ]  # revisão repetida entra uma vez só
    avisos = {a["documento"]: a["aviso"] for a in r["arquivos"]}
    assert avisos[f"{OBRA}-ARQ-PE-001"] is None
    assert "EM REVISÃO" in avisos[f"{OBRA}-EST-PE-001"]
    assert all(a["tamanho"] for a in r["arquivos"])
    assert r["recusadas"] == []


def test_obra_nao_recebe_o_que_esta_em_analise(cliente, c):
    r = _lote(cliente, c["campo"], [c["liberada"], c["em_revisao"], 999999])
    assert {a["documento"] for a in r["arquivos"]} == {f"{OBRA}-ARQ-PE-001"}
    # O que a obra não vê nem existe para ela: "não encontrada", como no avulso.
    assert [x["motivos"] for x in r["recusadas"]] == [["Revisão não encontrada."]] * 2


def test_cada_arquivo_baixado_pelo_avulso_fica_no_registro(cliente, admin, c):
    arquivo = _lote(cliente, c["campo"], [c["liberada"]])["arquivos"][0]
    r = cliente.get(f"/arquivos/{arquivo['id']}/download", headers=c["campo"])
    assert r.status_code == 200 and r.json()["nome_arquivo"] == arquivo["nome"]
    eventos = cliente.get(f"/obras/{c['obra']['id']}/eventos?acao=download", headers=admin).json()
    itens = eventos["itens"] if isinstance(eventos, dict) else eventos
    assert any((e.get("detalhes") or {}).get("arquivo") == arquivo["nome"] for e in itens)


def test_lote_vazio_ou_grande_demais_e_recusado(cliente, c):
    assert cliente.post("/revisoes/arquivos-lote", json={"revisao_ids": []}, headers=c["coord"]).status_code == 422
    grande = list(range(1, 1002))
    assert cliente.post("/revisoes/arquivos-lote", json={"revisao_ids": grande}, headers=c["coord"]).status_code == 422
