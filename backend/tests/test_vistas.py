"""Vistas do modelo 3D e pedido de correção com projetistas marcados
(TREELE, 21/10/2026)."""

from urllib.parse import urlsplit

import pytest

from .conftest import autenticar, enviar_arquivo

SENHA = "senha-vista-12345"
IFC = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n" + b" " * 300
PDF = b"%PDF-1.7\n" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 500
CAMERA = {"posicao": [10.0, 20.0, 30.0], "alvo": [0.0, 0.0, 0.0]}


def _pessoa(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@vista.teste.com.br"
    u = cliente.post("/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA},
                     headers=admin).json()
    cliente.post(f"/obras/{obra['id']}/membros", json={"usuario_id": u["id"], "papel": papel}, headers=admin)
    return u["id"], autenticar(cliente, email, SENHA)


def _put(cliente, url, conteudo):
    partes = urlsplit(url)
    assert cliente.put(f"{partes.path}?{partes.query}", content=conteudo).status_code == 200


@pytest.fixture(scope="module")
def c(cliente, admin):
    obra = cliente.post("/obras", json={"codigo": "VST", "nome": "Obra vistas", "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"}, headers=admin).json()
    outra = cliente.post("/obras", json={"codigo": "VIX", "nome": "Outra", "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"}, headers=admin).json()
    _, coord = _pessoa(cliente, admin, obra, "coordvis", "coordenador")
    proj_id, proj = _pessoa(cliente, admin, obra, "projvis", "projetista")
    proj2_id, proj2 = _pessoa(cliente, admin, obra, "projdois", "projetista")
    campo_id, campo = _pessoa(cliente, admin, obra, "campovis", "obra")
    # ARQ liberada (IFC + PDF), enviada pelo projetista; HID só em revisão.
    ifc = enviar_arquivo(cliente, proj, obra["id"], "VST-ARQ-PE-MOD-R00.ifc", IFC).json()
    enviar_arquivo(cliente, proj, obra["id"], "VST-ARQ-PE-MOD-R00.pdf", PDF)
    r = cliente.post(f"/revisoes/{ifc['revisao']['id']}/publicar", json={"avisar": False}, headers=coord)
    assert r.status_code == 200, r.text
    hid = enviar_arquivo(cliente, proj, obra["id"], "VST-HID-PE-MOD-R00.ifc", IFC).json()
    fora = enviar_arquivo(cliente, admin, outra["id"], "VIX-ARQ-PE-MOD-R00.ifc", IFC).json()
    return {
        "obra": obra, "coord": coord, "proj": proj, "proj2": proj2, "campo": campo,
        "proj_id": proj_id, "proj2_id": proj2_id, "campo_id": campo_id,
        "arq": ifc["arquivo"]["id"],
        "arq_doc": cliente.get(f"/obras/{obra['id']}/documentos?busca=VST-ARQ-PE-MOD",
                               headers=coord).json()["itens"][0]["id"],
        "hid": hid["arquivo"]["id"], "fora": fora["arquivo"]["id"],
    }


def _vista(cliente, cab, obra_id, arquivos, imagem=True, **extra):
    corpo = {"titulo": "Pilar invadindo a porta", "arquivos": arquivos, "camera": CAMERA, **extra}
    r = cliente.post(f"/obras/{obra_id}/vistas", json=corpo, headers=cab)
    if r.status_code != 201 or not imagem:
        return r
    _put(cliente, r.json()["envio_imagem"]["url"], PNG)
    return cliente.post(f"/vistas/{r.json()['vista']['id']}/imagem", headers=cab)


def test_vista_guarda_a_cena_e_a_imagem(cliente, c):
    r = _vista(cliente, c["coord"], c["obra"]["id"], [c["arq"], c["hid"]],
               cortes=[{"normal": [0, 0, 1], "ponto": [0, 0, 3]}],
               selecao={str(c["arq"]): ["2O2Fr$t4X7Zf8NOew3FLOH"], "999": ["x"]}, ocultos=[c["hid"]])
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["arquivos"] == [c["arq"], c["hid"]]
    assert {k: v["camera"][k] for k in CAMERA} == CAMERA and v["camera"]["fov"] is None
    assert v["selecao"] == {str(c["arq"]): ["2O2Fr$t4X7Zf8NOew3FLOH"]}  # modelo fora da cena sai
    assert v["ocultos"] == [c["hid"]] and v["imagem_url"]
    assert [m["documento"] for m in v["modelos"]] == ["VST-ARQ-PE-MOD", "VST-HID-PE-MOD"]
    # Quem é da obra abre; quem não é, não.
    assert cliente.get(f"/vistas/{v['id']}", headers=c["campo"]).status_code == 200
    assert v["id"] in [x["id"] for x in cliente.get(f"/obras/{c['obra']['id']}/vistas", headers=c["proj"]).json()]


def test_vista_so_leva_o_que_a_pessoa_pode_abrir(cliente, c):
    # A obra não abre o HID em análise; e ninguém põe modelo de outra obra.
    assert _vista(cliente, c["campo"], c["obra"]["id"], [c["hid"]], imagem=False).status_code == 403
    assert _vista(cliente, c["coord"], c["obra"]["id"], [c["fora"]], imagem=False).status_code == 422


def test_vista_sem_imagem_nao_aparece_e_nao_vai_para_pedido(cliente, c):
    r = _vista(cliente, c["coord"], c["obra"]["id"], [c["arq"]], imagem=False)
    vid = r.json()["vista"]["id"]
    assert vid not in [x["id"] for x in cliente.get(f"/obras/{c['obra']['id']}/vistas", headers=c["coord"]).json()]
    assert cliente.post(f"/vistas/{vid}/imagem", headers=c["coord"]).status_code == 409
    pedido = cliente.post(f"/documentos/{c['arq_doc']}/solicitacoes",
                          json={"descricao": "Corrigir o pilar P12 na porta.", "vista_id": vid}, headers=c["coord"])
    assert pedido.status_code == 422


def test_coordenador_pede_correcao_com_vista_e_marca_projetista(cliente, c):
    vid = _vista(cliente, c["coord"], c["obra"]["id"], [c["arq"]]).json()["id"]
    for cab in (c["proj"], c["proj2"]):
        cliente.post("/notificacoes/lidas", headers=cab)
    r = cliente.post(f"/documentos/{c['arq_doc']}/solicitacoes", headers=c["coord"], json={
        "descricao": "O pilar P12 invade o vão da porta da sala. Ajustar a arquitetura.",
        "vista_id": vid, "mencionados": [c["proj2_id"]],
    })
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["status"] == "autorizada" and s["vista_id"] == vid
    assert [u["nome"] for u in s["mencionados"]] == ["Projdois"]
    anexo = s["anexos"][0]
    assert anexo["nome_original"] == "Vista 3D - Pilar invadindo a porta.png"
    assert anexo["content_type"] == "image/png" and anexo["tamanho"] == len(PNG)
    # A imagem é uma cópia: abre pelo anexo como qualquer foto.
    v = cliente.get(f"/anexos/{anexo['id']}/visualizar", headers=c["proj2"])
    assert v.status_code == 200, v.text
    # Avisados: o projetista da última revisão e o marcado, com a menção à vista.
    for cab in (c["proj"], c["proj2"]):
        avisos = [a for a in cliente.get("/notificacoes", headers=cab).json() if not a["lida"]]
        assert any("vista marcada do modelo 3D" in a["texto"] for a in avisos), avisos


def test_so_coordenador_marca_e_so_projetista_e_marcado(cliente, c):
    corpo = {"descricao": "A porta da sala está errada no modelo.", "mencionados": [c["proj_id"]]}
    r = cliente.post(f"/documentos/{c['arq_doc']}/solicitacoes", json=corpo, headers=c["campo"])
    assert r.status_code == 403
    corpo["mencionados"] = [c["campo_id"]]
    r = cliente.post(f"/documentos/{c['arq_doc']}/solicitacoes", json=corpo, headers=c["coord"])
    assert r.status_code == 422


def test_obra_pede_correcao_com_vista(cliente, c):
    vid = _vista(cliente, c["campo"], c["obra"]["id"], [c["arq"]]).json()["id"]
    r = cliente.post(f"/documentos/{c['arq_doc']}/solicitacoes", headers=c["campo"],
                     json={"descricao": "Na obra a porta não cabe: ver a vista.", "vista_id": vid})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "aberta" and r.json()["vista_id"] == vid and len(r.json()["anexos"]) == 1


def test_coordenador_reprova_com_vista(cliente, c):
    vid = _vista(cliente, c["coord"], c["obra"]["id"], [c["hid"]]).json()["id"]
    modelo = cliente.get(f"/arquivos/{c['hid']}/modelo", headers=c["coord"]).json()
    cliente.post("/notificacoes/lidas", headers=c["proj"])
    # Vista inexistente ou sem imagem não entra.
    r = cliente.post(f"/revisoes/{modelo['revisao_id']}/reprovar", headers=c["coord"],
                     json={"observacao": "Tubulação passa pela viga.", "vista_id": 999999})
    assert r.status_code == 422
    r = cliente.post(f"/revisoes/{modelo['revisao_id']}/reprovar", headers=c["coord"],
                     json={"observacao": "A tubulação de esgoto atravessa a viga V12.", "vista_id": vid})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "reprovado" and r.json()["vista_reprovacao_id"] == vid
    avisos = [a for a in cliente.get("/notificacoes", headers=c["proj"]).json() if not a["lida"]]
    assert any("vista marcada do modelo 3D" in a["texto"] for a in avisos), avisos


def test_vista_guarda_as_marcacoes_e_o_angulo(cliente, c):
    corpo = {"titulo": "Com marcações", "arquivos": [c["arq"]], "com_marcacoes": True,
             "camera": {**CAMERA, "fov": 60.0}}
    r = cliente.post(f"/obras/{c['obra']['id']}/vistas", json=corpo, headers=c["coord"])
    assert r.status_code == 201, r.text
    criada = r.json()
    assert criada["envio_marcacoes"]
    _put(cliente, criada["envio_imagem"]["url"], PNG)
    _put(cliente, criada["envio_marcacoes"]["url"], PNG + b"marcas")
    v = cliente.post(f"/vistas/{criada['vista']['id']}/imagem", headers=c["coord"]).json()
    assert v["marcacoes_url"] and v["camera"]["fov"] == 60.0
    # Sem as marcações (pedidas mas não enviadas), a vista vale só com a foto.
    sem = cliente.post(f"/obras/{c['obra']['id']}/vistas", json=corpo, headers=c["coord"]).json()
    _put(cliente, sem["envio_imagem"]["url"], PNG)
    v2 = cliente.post(f"/vistas/{sem['vista']['id']}/imagem", headers=c["coord"]).json()
    assert v2["imagem_url"] and v2["marcacoes_url"] is None
