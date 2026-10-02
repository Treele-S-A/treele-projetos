"""Solicitação de revisão (TREELE, 02/10/2026).

Coordenador e obra pedem alteração num projeto liberado, com descrição
obrigatória e, se quiserem, fotos ou PDFs. O pedido fecha quando a revisão
nova é liberada.
"""

from urllib.parse import urlsplit

import pytest

from app.services.storage import armazenamento

from .conftest import autenticar, enviar_arquivo

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


def test_fecha_quando_a_revisao_nova_e_liberada(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "009")
    _pedir(cliente, pessoas["campo"], doc)
    _pedir(cliente, pessoas["coord"], doc, "Também ajustar a cota do peitoril.")

    # Revisão nova enviada, mas ainda não liberada: o pedido continua aberto.
    r01 = enviar_arquivo(cliente, admin, obra["id"], "SOL-ARQ-PE-009-R01.pdf", PDF)
    detalhe = cliente.get(f"/documentos/{doc}", headers=admin).json()
    assert detalhe["solicitacoes_abertas"] == 2

    cliente.post(f"/revisoes/{r01.json()['revisao']['id']}/publicar", json={}, headers=admin)

    detalhe = cliente.get(f"/documentos/{doc}", headers=admin).json()
    assert detalhe["solicitacoes_abertas"] == 0
    assert {s["status"] for s in detalhe["solicitacoes"]} == {"atendida"}
    assert {s["atendida_por_numero"] for s in detalhe["solicitacoes"]} == {"01"}


def test_pedido_atendido_nao_aceita_anexo(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "010")
    sol = _pedir(cliente, pessoas["campo"], doc).json()["id"]
    r01 = enviar_arquivo(cliente, admin, obra["id"], "SOL-ARQ-PE-010-R01.pdf", PDF)
    cliente.post(f"/revisoes/{r01.json()['revisao']['id']}/publicar", json={}, headers=admin)
    assert _anexar(cliente, pessoas["campo"], sol, "tarde.png", PNG).status_code == 409


def test_excluir_documento_leva_os_anexos(cliente, admin, obra, pessoas):
    doc = _liberado(cliente, admin, obra, "011")
    sol = _pedir(cliente, pessoas["campo"], doc).json()["id"]
    _anexar(cliente, pessoas["campo"], sol, "foto.png", PNG)
    detalhe = cliente.get(f"/documentos/{doc}", headers=admin).json()
    anexo = detalhe["solicitacoes"][0]["anexos"][0]["id"]
    from app.db import SessionLocal
    from app.models import AnexoSolicitacao

    with SessionLocal() as db:
        chave = db.get(AnexoSolicitacao, anexo).storage_key
    assert armazenamento.info(chave)[0]

    cliente.delete(f"/revisoes/{detalhe['revisoes'][0]['id']}", headers=admin)

    assert not armazenamento.info(chave)[0]
