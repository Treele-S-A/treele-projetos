"""Solicitação de revisão (TREELE, 02/10/2026).

Coordenador e obra pedem alteração num projeto liberado, com descrição
obrigatória e, se quiserem, fotos ou PDFs. O pedido fecha quando a revisão
nova é liberada.
"""

from urllib.parse import urlsplit

import pytest

from .conftest import autenticar, autorizar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
PEDIDO = "Compatibilizar o shaft do banheiro com a viga V12."


def _usuario(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@sol.teste.com.br"
    r = cliente.post(
        "/usuarios",
        json={"nome": apelido.title(), "email": email, "senha": "senha-sol-12345"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    if papel:
        cliente.post(
            f"/obras/{obra['id']}/membros",
            json={"usuario_id": r.json()["id"], "papel": papel},
            headers=admin,
        )
    return autenticar(cliente, email, "senha-sol-12345")


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": "SOL", "nome": "Obra solicitação"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def pessoas(cliente, admin, obra):
    return {
        "campo": _usuario(cliente, admin, obra, "campo", "obra"),
        "proj": _usuario(cliente, admin, obra, "projetista", "projetista"),
        "coord": _usuario(cliente, admin, obra, "coordenador", "coordenador"),
    }


def _liberado(cliente, admin, obra, prancha, rev="00"):
    r = enviar_arquivo(cliente, admin, obra["id"], f"SOL-ARQ-PE-{prancha}-R{rev}.pdf", PDF)
    assert r.status_code == 200, r.text
    p = cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={}, headers=admin)
    assert p.status_code == 200, p.text
    lista = cliente.get(
        f"/obras/{obra['id']}/documentos?busca=SOL-ARQ-PE-{prancha}", headers=admin
    ).json()
    return lista["itens"][0]["id"]


def _pedir(cliente, cab, doc_id, descricao=PEDIDO):
    return cliente.post(f"/documentos/{doc_id}/solicitacoes", json={"descricao": descricao}, headers=cab)


def _anexar(cliente, cab, solicitacao_id, nome, conteudo):
    r = cliente.post(
        f"/solicitacoes/{solicitacao_id}/anexos",
        json={"nome_arquivo": nome, "tamanho": len(conteudo)},
        headers=cab,
    )
    if r.status_code != 201:
        return r
    partes = urlsplit(r.json()["url"])
    assert cliente.put(f"{partes.path}?{partes.query}", content=conteudo).status_code == 200
    return cliente.post(f"/anexos/{r.json()['anexo_id']}/confirmar", headers=cab)


# ------------------------------------------------------------ pedir


def test_obra_pede_revisao_com_descricao(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "001")

    r = _pedir(cliente, pessoas["campo"], doc)

    assert r.status_code == 201, r.text
    assert r.json()["descricao"] == PEDIDO
    assert r.json()["status"] == "aberta"
    assert r.json()["revisao_numero"] == "00"

    # A marca aparece ao lado do status, na lista e no documento.
    lista = cliente.get(f"/obras/{obra['id']}/documentos?busca=SOL-ARQ-PE-001", headers=admin)
    assert lista.json()["itens"][0]["solicitacoes_abertas"] == 1
    detalhe = cliente.get(f"/documentos/{doc}", headers=pessoas["proj"]).json()
    assert detalhe["solicitacoes"][0]["descricao"] == PEDIDO
    assert detalhe["revisao_atual"]["status"] == "liberado_para_obra"


def test_coordenador_tambem_pede(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "002")
    assert _pedir(cliente, pessoas["coord"], doc).status_code == 201


def test_descricao_e_obrigatoria(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "003")
    assert _pedir(cliente, pessoas["campo"], doc, "").status_code == 422
    assert _pedir(cliente, pessoas["campo"], doc, "mudar").status_code == 422


def test_projetista_nao_pede(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "004")
    assert _pedir(cliente, pessoas["proj"], doc).status_code == 403


def test_so_se_pede_revisao_de_projeto_liberado(cliente, admin, obra, pessoas):
    enviar_arquivo(cliente, admin, obra["id"], "SOL-ARQ-PE-005-R00.pdf", PDF)
    doc = cliente.get(
        f"/obras/{obra['id']}/documentos?busca=SOL-ARQ-PE-005", headers=admin
    ).json()["itens"][0]["id"]
    assert _pedir(cliente, pessoas["coord"], doc).status_code == 409


def test_comercial_nao_ve_nem_pede(cliente, admin, obra):
    cliente.post(
        "/usuarios",
        json={
            "nome": "Com", "email": "com-sol@teste.com.br", "senha": "senha-com-sol1",
            "comercial": True,
        },
        headers=admin,
    )
    comercial = autenticar(cliente, "com-sol@teste.com.br", "senha-com-sol1")
    r = enviar_arquivo(cliente, admin, obra["id"], "SOL-COM-PE-001-R00.pdf", PDF)
    cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={}, headers=admin)
    doc = cliente.get(
        f"/obras/{obra['id']}/documentos?busca=SOL-COM-PE-001", headers=admin
    ).json()["itens"][0]["id"]
    _pedir(cliente, admin, doc)

    assert _pedir(cliente, comercial, doc).status_code == 403
    detalhe = cliente.get(f"/documentos/{doc}", headers=comercial).json()
    assert detalhe["solicitacoes"] == []
    assert detalhe["solicitacoes_abertas"] == 0


# ------------------------------------------------------------ anexos


def test_anexa_foto_e_pdf_e_abre_no_navegador(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "006")
    sol = _pedir(cliente, pessoas["campo"], doc).json()["id"]

    assert _anexar(cliente, pessoas["campo"], sol, "foto do shaft.png", PNG).status_code == 200
    assert _anexar(cliente, pessoas["campo"], sol, "planta marcada.pdf", PDF).status_code == 200

    anexos = cliente.get(f"/documentos/{doc}", headers=pessoas["proj"]).json()["solicitacoes"][0]["anexos"]
    assert [a["nome_original"] for a in anexos] == ["foto do shaft.png", "planta marcada.pdf"]

    url = cliente.get(f"/anexos/{anexos[0]['id']}/visualizar", headers=pessoas["proj"]).json()["url"]
    partes = urlsplit(url)
    aberto = cliente.get(f"{partes.path}?{partes.query}")
    assert aberto.headers["content-type"] == "image/png"
    assert aberto.headers["content-disposition"].startswith("inline")


def test_anexo_so_foto_ou_pdf(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "007")
    sol = _pedir(cliente, pessoas["campo"], doc).json()["id"]
    assert _anexar(cliente, pessoas["campo"], sol, "planilha.xlsx", b"PK" * 50).status_code == 415


def test_so_quem_pediu_anexa(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "008")
    sol = _pedir(cliente, pessoas["campo"], doc).json()["id"]
    assert _anexar(cliente, pessoas["coord"], sol, "foto.png", PNG).status_code == 403


# ------------------------------------------------------------ fechar


def _liberar(cliente, admin, revisao_id, atendidas=()):
    return cliente.post(
        f"/revisoes/{revisao_id}/publicar",
        json={"solicitacoes_atendidas": list(atendidas)},
        headers=admin,
    )


def _por_id(cliente, admin, doc):
    detalhe = cliente.get(f"/documentos/{doc}", headers=admin).json()
    return {s["id"]: s for s in detalhe["solicitacoes"]}, detalhe


def _autorizar(cliente, cab, solicitacao_id):
    r = cliente.post(f"/solicitacoes/{solicitacao_id}/autorizar", headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def test_marcadas_na_liberacao_fecham_e_as_outras_seguem_abertas(cliente, admin, obra, pessoas):
    """Quem libera marca quais pedidos a revisão nova atende (02/10/2026)."""
    doc = _liberado(cliente, admin, obra, "009")
    ralo = _pedir(cliente, pessoas["campo"], doc).json()["id"]
    _autorizar(cliente, pessoas["coord"], ralo)
    peitoril = _pedir(cliente, pessoas["coord"], doc, "Também ajustar a cota do peitoril.").json()["id"]

    # Revisão nova enviada, ainda não liberada: tudo continua autorizado.
    r01 = enviar_arquivo(cliente, admin, obra["id"], "SOL-ARQ-PE-009-R01.pdf", PDF)
    assert r01.status_code == 200, r01.text
    assert cliente.get(f"/documentos/{doc}", headers=admin).json()["solicitacoes_autorizadas"] == 2

    r = _liberar(cliente, admin, r01.json()["revisao"]["id"], atendidas=[ralo])
    assert r.status_code == 200, r.text

    pedidos, detalhe = _por_id(cliente, admin, doc)
    assert pedidos[ralo]["status"] == "atendida"
    assert pedidos[ralo]["atendida_por_numero"] == "01"
    assert pedidos[peitoril]["status"] == "autorizada"
    assert detalhe["solicitacoes_autorizadas"] == 1

    evento = cliente.get(f"/obras/{obra['id']}/eventos", headers=admin).json()["itens"][0]
    assert evento["acao"] == "revisao_publicada"
    assert evento["detalhes"]["solicitacoes_atendidas"] == [ralo]


def test_liberar_sem_marcar_nada_deixa_tudo_aberto(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "012")
    _autorizar(cliente, admin, _pedir(cliente, pessoas["campo"], doc).json()["id"])
    r01 = enviar_arquivo(cliente, admin, obra["id"], "SOL-ARQ-PE-012-R01.pdf", PDF)
    _liberar(cliente, admin, r01.json()["revisao"]["id"])
    assert cliente.get(f"/documentos/{doc}", headers=admin).json()["solicitacoes_autorizadas"] == 1


def test_pedido_de_outro_documento_nao_libera_nada(cliente, admin, obra, pessoas):
    doc_a = _liberado(cliente, admin, obra, "014")
    _liberado(cliente, admin, obra, "015")
    de_outro = _pedir(cliente, pessoas["campo"], doc_a).json()["id"]
    _autorizar(cliente, admin, de_outro)
    r01 = enviar_arquivo(cliente, admin, obra["id"], "SOL-ARQ-PE-015-R01.pdf", PDF,
                         autorizar_com=admin)

    r = _liberar(cliente, admin, r01.json()["revisao"]["id"], atendidas=[de_outro])

    assert r.status_code == 422
    revisao = cliente.get(f"/revisoes/{r01.json()['revisao']['id']}", headers=admin).json()
    assert revisao["status"] == "em_revisao"
    pedidos, _ = _por_id(cliente, admin, doc_a)
    assert pedidos[de_outro]["status"] == "autorizada"


def test_pedido_ja_atendido_nao_e_marcado_de_novo(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "016")
    sol = _pedir(cliente, pessoas["campo"], doc).json()["id"]
    _autorizar(cliente, admin, sol)
    r01 = enviar_arquivo(cliente, admin, obra["id"], "SOL-ARQ-PE-016-R01.pdf", PDF)
    _liberar(cliente, admin, r01.json()["revisao"]["id"], atendidas=[sol])
    r02 = enviar_arquivo(cliente, admin, obra["id"], "SOL-ARQ-PE-016-R02.pdf", PDF,
                         autorizar_com=admin)
    assert _liberar(cliente, admin, r02.json()["revisao"]["id"], atendidas=[sol]).status_code == 422


def test_pasta_traz_os_pedidos_para_quem_libera_por_la(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "017")
    sol = _pedir(cliente, pessoas["campo"], doc).json()["id"]
    pasta = cliente.get(f"/obras/{obra['id']}/pastas/ARQ/PE", headers=admin).json()
    item = next(d for d in pasta["documentos"] if d["id"] == doc)
    assert [s["id"] for s in item["solicitacoes"]] == [sol]


def test_pedido_atendido_nao_aceita_anexo(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "010")
    sol = _pedir(cliente, pessoas["campo"], doc).json()["id"]
    _autorizar(cliente, admin, sol)
    r01 = enviar_arquivo(cliente, admin, obra["id"], "SOL-ARQ-PE-010-R01.pdf", PDF)
    _liberar(cliente, admin, r01.json()["revisao"]["id"], atendidas=[sol])
    assert _anexar(cliente, pessoas["campo"], sol, "tarde.png", PNG).status_code == 409
