"""Conflitos do 3D na correção de projeto (TREELE, 16/11/2026): um pedido de
revisão ou uma reprovação trata vários conflitos de uma vez, e eles vão para a
ata de análise crítica — na revisão que traz a correção, congelados com a
situação do dia; na revisão reprovada, junto com o motivo."""

from app.config import settings

from .conftest import autenticar, enviar_arquivo

SENHA = "senha-conflito-ata-12345"
IFC = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n" + b" " * 300
CONFIG = {
    "a": {"disciplinas": ["HID"], "categorias": [], "excluir": []},
    "b": {"disciplinas": ["EST"], "categorias": ["IFCCOLUMN", "IFCBEAM"]},
    "modo": "interferencia", "tolerancia": 0.01, "folga": 0.05, "ignorarMesmoModelo": True,
}


def _pessoa(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@conflitoata.teste.com.br"
    u = cliente.post("/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA}, headers=admin).json()
    cliente.post(f"/obras/{obra}/membros", json={"usuario_id": u["id"], "papel": papel}, headers=admin)
    return autenticar(cliente, email, SENHA)


def _achado(hid, est, guid_a, guid_b, nome_b):
    return {"arquivo_a_id": hid, "arquivo_b_id": est, "guids_a": [guid_a], "guid_b": guid_b,
            "categoria_a": "IFCPIPESEGMENT", "categoria_b": "IFCBEAM", "nome_a": "Tubo 100", "nome_b": nome_b,
            "centro": [1, 6.12, 3], "caixa_min": [0, 6, 2], "caixa_max": [2, 6.3, 4], "medida": 0.035}


def _doc(cliente, cab, obra, codigo):
    return cliente.get(f"/obras/{obra}/documentos?busca={codigo}", headers=cab).json()["itens"][0]["id"]


def _respostas(grupo):
    return [{"id": i["id"], "resposta": "S"} for g in grupo["formulario"]["grupos"] for i in g["itens"]]


def test_pedido_e_reprovacao_com_varios_conflitos_vao_para_a_ata(cliente, admin, monkeypatch):
    monkeypatch.setattr(settings, "ata_analise_obrigatoria", False)
    obra = cliente.post("/obras", json={"codigo": "CNA", "nome": "Obra conflitos na ata",
                                        "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"}, headers=admin).json()["id"]
    coord = _pessoa(cliente, admin, obra, "coordcna", "coordenador")
    proj = _pessoa(cliente, admin, obra, "projcna", "projetista")
    campo = _pessoa(cliente, admin, obra, "campocna", "obra")
    arq, rev, doc = {}, {}, {}
    for disc in ("EST", "HID"):
        r = enviar_arquivo(cliente, proj, obra, f"CNA-{disc}-PE-MOD-R00.ifc", IFC).json()
        assert cliente.post(f"/revisoes/{r['revisao']['id']}/publicar", json={"avisar": False},
                            headers=coord).status_code == 200
        arq[disc], rev[disc] = r["arquivo"]["id"], r["revisao"]["id"]
        doc[disc] = _doc(cliente, coord, obra, f"CNA-{disc}-PE-MOD")

    conjunto = cliente.post(f"/obras/{obra}/conjuntos-conflito", json={
        "nome": "Instalações × pilares e vigas", "pronto": "instalacoes-estrutura", "config": CONFIG,
    }, headers=proj).json()["id"]
    r = cliente.post(f"/conjuntos-conflito/{conjunto}/rodadas", json={
        "arquivos": [arq["EST"], arq["HID"]],
        "achados": [_achado(arq["HID"], arq["EST"], f"t{i}", f"v{i}", f"V{i}") for i in (1, 2, 3)],
    }, headers=proj)
    assert r.status_code == 200, r.text
    c1, c2, c3 = r.json()["ids"]

    # Um pedido só para dois conflitos, com o BCF anexado.
    url = f"/documentos/{doc['HID']}/solicitacoes"
    texto = "Desviar os tubos que atravessam as vigas V1 e V2 do térreo."
    assert cliente.post(url, json={"descricao": texto, "conflito_ids": [999999]}, headers=coord).status_code == 422
    r = cliente.post(url, json={"descricao": texto, "conflito_ids": [c1, c2, c1]}, headers=coord)
    assert r.status_code == 201, r.text
    pedido = r.json()
    assert pedido["status"] == "autorizada"
    assert [c["id"] for c in pedido["conflitos"]] == [c1, c2]
    assert "Tubo: Tubo 100 (CNA-HID-PE-MOD R00) × Viga: V1" in pedido["conflitos"][0]["texto"]
    anexo = cliente.post(f"/solicitacoes/{pedido['id']}/anexos",
                         json={"nome_arquivo": "CNA-conflitos.bcfzip", "tamanho": 2048}, headers=coord)
    assert anexo.status_code == 201, anexo.text
    # A obra também pede a partir de conflitos (vai para autorização).
    r = cliente.post(url, json={"descricao": "Conferir o tubo que bate na viga V3.", "conflito_ids": [c3]}, headers=campo)
    assert r.status_code == 201 and r.json()["status"] == "aberta"

    # R01 da hidráulica; a detecção com ela resolve o c1, o c2 continua.
    r01 = enviar_arquivo(cliente, proj, obra, "CNA-HID-PE-MOD-R01.ifc", IFC).json()
    r = cliente.post(f"/conjuntos-conflito/{conjunto}/rodadas", json={
        "arquivos": [arq["EST"], r01["arquivo"]["id"]],
        "achados": [_achado(r01["arquivo"]["id"], arq["EST"], f"t{i}", f"v{i}", f"V{i}") for i in (2, 3)],
    }, headers=proj)
    assert r.status_code == 200, r.text
    # Conflito resolvido não entra em pedido novo.
    r = cliente.post(f"/documentos/{doc['EST']}/solicitacoes",
                     json={"descricao": "Rever a viga do conflito resolvido.", "conflito_ids": [c1]}, headers=coord)
    assert r.status_code == 422 and "resolvido" in r.json()["detail"]

    monkeypatch.setattr(settings, "ata_analise_obrigatoria", True)
    grupo = cliente.post("/atas/pendentes", json={"revisao_ids": [r01["revisao"]["id"]]}, headers=coord).json()[0]
    assert len(grupo["conflitos"]) == 1
    origem = grupo["conflitos"][0]
    assert origem["tipo"] == "solicitacao" and origem["origem"] == "Pedido de revisão sobre a R00"
    situacao = {c["id"]: (c["situacao"], c["conferido"]) for c in origem["conflitos"]}
    assert situacao == {c1: ("resolvido", True), c2: ("ativo", True)}

    r = cliente.post("/atas", json={"revisao_ids": [r01["revisao"]["id"]], "respostas": _respostas(grupo)}, headers=coord)
    assert r.status_code == 201, r.text
    ata = r.json()
    assert ata["resultado"] == "conforme"
    assert [c["id"] for c in ata["conflitos"][0]["conflitos"]] == [c1, c2]

    # A ata não muda: o c2 aprovado depois continua "ativo" nela.
    assert cliente.patch(f"/conflitos/{c2}", json={"status": "aprovado", "justificativa": "Furo previsto pelo calculista."},
                         headers=coord).status_code == 200
    ata = cliente.get(f"/atas/{ata['id']}", headers=coord).json()
    assert {c["id"]: c["situacao"] for c in ata["conflitos"][0]["conflitos"]}[c2] == "ativo"

    # Reprovada apontando o c3: a "Solicitação de alterações" da ata o mostra.
    r = cliente.post(f"/revisoes/{r01['revisao']['id']}/reprovar",
                     json={"observacao": "O tubo ainda bate na viga V3.", "conflito_ids": [c3]}, headers=coord)
    assert r.status_code == 200, r.text
    ata = cliente.get(f"/atas/{ata['id']}", headers=coord).json()
    assert [c["id"] for c in ata["situacao"][0]["conflitos"]] == [c3]
    pdf = cliente.get(f"/atas/{ata['id']}/pdf", headers=coord)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # A R02 traz a correção das duas origens: o pedido (ainda aberto) e a
    # reprovação da R01. A detecção ainda não rodou com a R02.
    r02 = enviar_arquivo(cliente, proj, obra, "CNA-HID-PE-MOD-R02.ifc", IFC).json()
    grupo = cliente.post("/atas/pendentes", json={"revisao_ids": [r02["revisao"]["id"]]}, headers=coord).json()[0]
    assert [o["origem"] for o in grupo["conflitos"]] == ["Pedido de revisão sobre a R00", "Reprovação da R01"]
    c3_linha = grupo["conflitos"][1]["conflitos"][0]
    assert c3_linha["situacao"] == "ativo" and c3_linha["conferido"] is False and c3_linha["revisao_vista"] == "01"
    r = cliente.post("/atas", json={"revisao_ids": [r02["revisao"]["id"]], "respostas": _respostas(grupo)}, headers=coord)
    assert r.status_code == 201, r.text
    pdf = cliente.get(f"/atas/{r.json()['id']}/pdf", headers=coord)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_conflito_de_outro_documento_nao_entra(cliente, admin, monkeypatch):
    monkeypatch.setattr(settings, "ata_analise_obrigatoria", False)
    obra = cliente.post("/obras", json={"codigo": "CNB", "nome": "Obra conflitos B",
                                        "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"}, headers=admin).json()["id"]
    coord = _pessoa(cliente, admin, obra, "coordcnb", "coordenador")
    arq, doc = {}, {}
    for disc in ("EST", "HID", "ELE"):
        r = enviar_arquivo(cliente, coord, obra, f"CNB-{disc}-PE-MOD-R00.ifc", IFC).json()
        assert cliente.post(f"/revisoes/{r['revisao']['id']}/publicar", json={"avisar": False},
                            headers=coord).status_code == 200
        arq[disc], doc[disc] = r["arquivo"]["id"], _doc(cliente, coord, obra, f"CNB-{disc}-PE-MOD")
    conjunto = cliente.post(f"/obras/{obra}/conjuntos-conflito", json={
        "nome": "Instalações × pilares e vigas", "pronto": "instalacoes-estrutura", "config": CONFIG,
    }, headers=coord).json()["id"]
    c1 = cliente.post(f"/conjuntos-conflito/{conjunto}/rodadas", json={
        "arquivos": [arq["EST"], arq["HID"]], "achados": [_achado(arq["HID"], arq["EST"], "t1", "v1", "V1")],
    }, headers=coord).json()["ids"][0]
    r = cliente.post(f"/documentos/{doc['ELE']}/solicitacoes",
                     json={"descricao": "Pedido com conflito que não é deste projeto.", "conflito_ids": [c1]},
                     headers=coord)
    assert r.status_code == 422 and "não envolve" in r.json()["detail"]
