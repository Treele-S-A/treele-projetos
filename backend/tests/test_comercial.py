"""Perfil comercial: todas as obras, só a disciplina COM, só o liberado, só baixar.

O teste importante aqui é o de tudo que ele NÃO consegue: o pedido foi "o mais
restrito possível". Cada porta da API que muda alguma coisa, ou que mostra o
que não é COM liberado, é testada fechada.
"""

import pytest

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200


def _obra(cliente, admin, codigo):
    r = cliente.post("/obras", json={"codigo": codigo, "nome": f"Obra {codigo}"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def _enviar(cliente, admin, obra, disc, prancha, rev, liberar):
    nome = f"{obra['codigo']}-{disc}-PE-{prancha}-R{rev}.pdf"
    r = enviar_arquivo(cliente, admin, obra["id"], nome, PDF,
                       autorizar_com=admin if rev != "00" else None)
    assert r.status_code == 200, r.text
    corpo = r.json()
    if liberar:
        p = cliente.post(f"/revisoes/{corpo['revisao']['id']}/publicar", json={}, headers=admin)
        assert p.status_code == 200, p.text
    return corpo


@pytest.fixture(scope="module")
def cenario(cliente, admin):
    a = _obra(cliente, admin, "CMA")
    b = _obra(cliente, admin, "CMB")
    return {
        "a": a,
        "b": b,
        # COM liberado
        "com_ok": _enviar(cliente, admin, a, "COM", "001", "00", True),
        # COM com R00 liberada e R01 ainda em andamento
        "com_r00": _enviar(cliente, admin, a, "COM", "002", "00", True),
        "com_r01": _enviar(cliente, admin, a, "COM", "002", "01", False),
        # COM que nunca saiu de "em revisão"
        "com_rascunho": _enviar(cliente, admin, a, "COM", "003", "00", False),
        # outra disciplina, liberada
        "arq": _enviar(cliente, admin, a, "ARQ", "001", "00", True),
        # COM liberado na segunda obra
        "com_b": _enviar(cliente, admin, b, "COM", "001", "00", True),
    }


@pytest.fixture(scope="module")
def comercial(cliente, admin):
    r = cliente.post(
        "/usuarios",
        json={
            "nome": "Comercial", "email": "comercial@teste.com.br",
            "senha": "senha-comercial-1", "comercial": True,
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    assert r.json()["comercial"] is True
    return autenticar(cliente, "comercial@teste.com.br", "senha-comercial-1")


def _doc_id(cliente, admin, obra, codigo):
    return _codigos(cliente, admin, obra)[codigo]["id"]


def _codigos(cliente, cab, obra):
    r = cliente.get(f"/obras/{obra['id']}/documentos?por_pagina=200", headers=cab)
    assert r.status_code == 200, r.text
    return {d["codigo"]: d for d in r.json()["itens"]}


# ------------------------------------------------------------ o que ele vê


def test_ve_todas_as_obras_sem_estar_em_equipe(cliente, cenario, comercial):
    obras = {o["codigo"]: o for o in cliente.get("/obras", headers=comercial).json()}
    assert {"CMA", "CMB"} <= set(obras)
    assert obras["CMA"]["papel"] is None
    assert obras["CMA"]["permissoes"] == []


def test_lista_so_tem_com_liberado(cliente, cenario, comercial):
    docs = _codigos(cliente, comercial, cenario["a"])
    assert set(docs) == {"CMA-COM-PE-001", "CMA-COM-PE-002"}
    # A R01 em andamento não esconde a R00 liberada: ela é a atual para ele.
    assert docs["CMA-COM-PE-002"]["revisao_atual"]["numero"] == "00"
    assert docs["CMA-COM-PE-002"]["revisao_atual"]["status"] == "liberado_para_obra"
    assert "CMB-COM-PE-001" in _codigos(cliente, comercial, cenario["b"])


def test_arvore_so_tem_a_disciplina_com(cliente, cenario, comercial):
    arvore = cliente.get(f"/obras/{cenario['a']['id']}/arvore", headers=comercial).json()
    assert [d["codigo"] for d in arvore["disciplinas"]] == ["COM"]


def test_pasta_de_outra_disciplina_nao_existe(cliente, cenario, comercial):
    obra = cenario["a"]["id"]
    assert cliente.get(f"/obras/{obra}/pastas/ARQ/PE", headers=comercial).status_code == 404
    pasta = cliente.get(f"/obras/{obra}/pastas/COM/PE", headers=comercial).json()
    status = {r["status"] for d in pasta["documentos"] for r in d["revisoes"]}
    assert status == {"liberado_para_obra"}


def test_documento_mostra_so_a_revisao_liberada(cliente, admin, cenario, comercial):
    doc_id = _doc_id(cliente, admin, cenario["a"], "CMA-COM-PE-002")
    detalhe = cliente.get(f"/documentos/{doc_id}", headers=comercial).json()
    assert [r["numero"] for r in detalhe["revisoes"]] == ["00"]


def test_documento_fora_do_alcance_nao_existe(cliente, admin, cenario, comercial):
    for codigo in ("CMA-ARQ-PE-001", "CMA-COM-PE-003"):
        doc_id = _doc_id(cliente, admin, cenario["a"], codigo)
        assert cliente.get(f"/documentos/{doc_id}", headers=comercial).status_code == 404, codigo


def test_baixa_o_com_liberado(cliente, cenario, comercial):
    arquivo = cenario["com_ok"]["arquivo"]["id"]
    r = cliente.get(f"/arquivos/{arquivo}/download", headers=comercial)
    assert r.status_code == 200, r.text
    assert r.json()["aviso"] is None


def test_nao_baixa_outra_disciplina_nem_o_que_esta_em_andamento(cliente, cenario, comercial):
    arq = cenario["arq"]["arquivo"]["id"]
    assert cliente.get(f"/arquivos/{arq}/download", headers=comercial).status_code == 404
    andamento = cenario["com_r01"]["arquivo"]["id"]
    assert cliente.get(f"/arquivos/{andamento}/download", headers=comercial).status_code == 403
    rev = cenario["com_r01"]["revisao"]["id"]
    assert cliente.get(f"/revisoes/{rev}", headers=comercial).status_code == 404


def test_lista_mestra_so_tem_com(cliente, cenario, comercial):
    r = cliente.get(f"/obras/{cenario['a']['id']}/documentos/exportar", headers=comercial)
    assert r.status_code == 200
    assert "CMA-COM-PE-001" in r.text
    assert "CMA-ARQ-PE-001" not in r.text
    assert "CMA-COM-PE-003" not in r.text


# ------------------------------------------------------------ o que ele não faz


def test_nao_envia(cliente, cenario, comercial):
    obra = cenario["a"]["id"]
    r = cliente.post(
        f"/obras/{obra}/uploads/iniciar",
        json={"nome_arquivo": "CMA-COM-PE-009-R00.pdf", "tamanho": 10, "titulo": "Folder"},
        headers=comercial,
    )
    assert r.status_code == 403
    r = cliente.post(
        f"/obras/{obra}/nomenclatura/validar",
        json={"nomes": ["CMA-COM-PE-009-R00.pdf"]},
        headers=comercial,
    )
    assert r.status_code == 403


def test_nao_exclui_nem_libera_nem_cancela(cliente, admin, cenario, comercial):
    arquivo = cenario["com_ok"]["arquivo"]["id"]
    revisao = cenario["com_ok"]["revisao"]["id"]
    assert cliente.delete(f"/arquivos/{arquivo}", headers=comercial).status_code == 403
    assert cliente.delete(f"/revisoes/{revisao}", headers=comercial).status_code == 403
    assert cliente.post(f"/revisoes/{revisao}/cancelar", headers=comercial).status_code == 403
    assert (
        cliente.patch(f"/revisoes/{revisao}", json={"descricao": "x"}, headers=comercial).status_code
        == 403
    )
    doc = _doc_id(cliente, admin, cenario["a"], "CMA-COM-PE-001")
    assert (
        cliente.patch(f"/documentos/{doc}", json={"titulo": "Outro"}, headers=comercial).status_code
        == 403
    )


def test_nao_mexe_em_equipe_configuracao_nem_usuarios(cliente, cenario, comercial):
    obra = cenario["a"]["id"]
    assert cliente.get(f"/obras/{obra}/membros", headers=comercial).status_code == 403
    assert (
        cliente.post(
            f"/obras/{obra}/membros", json={"usuario_id": 1, "papel": "coordenador"},
            headers=comercial,
        ).status_code
        == 403
    )
    assert cliente.patch(f"/obras/{obra}", json={"nome": "X"}, headers=comercial).status_code == 403
    assert cliente.get(f"/obras/{obra}/padrao", headers=comercial).status_code == 403
    assert cliente.get(f"/obras/{obra}/eventos", headers=comercial).status_code == 403
    assert cliente.delete(f"/obras/{obra}/logo", headers=comercial).status_code == 403
    assert cliente.get("/usuarios", headers=comercial).status_code == 403
    assert (
        cliente.post(
            "/usuarios",
            json={"nome": "Outro", "email": "outro-com@teste.com.br", "senha": "senha-outra-12"},
            headers=comercial,
        ).status_code
        == 403
    )
    assert cliente.post("/obras", json={"codigo": "CMZ", "nome": "Nova"}, headers=comercial).status_code == 403
    assert (
        cliente.post("/disciplinas", json={"codigo": "XYZ", "nome": "Nova"}, headers=comercial).status_code
        == 403
    )


# ------------------------------------------------------------ cadastro


def test_comercial_nao_entra_em_equipe(cliente, admin, cenario, comercial):
    """Um papel na equipe daria permissões que o perfil não pode ter."""
    eu = cliente.get("/auth/eu", headers=comercial).json()
    r = cliente.post(
        f"/obras/{cenario['a']['id']}/membros",
        json={"usuario_id": eu["id"], "papel": "coordenador"},
        headers=admin,
    )
    assert r.status_code == 400


def test_administrador_e_comercial_ao_mesmo_tempo_e_recusado(cliente, admin):
    r = cliente.post(
        "/usuarios",
        json={
            "nome": "Ambos", "email": "ambos@teste.com.br", "senha": "senha-ambos-123",
            "admin": True, "comercial": True,
        },
        headers=admin,
    )
    assert r.status_code == 400


def test_disciplina_comercial_existe_no_catalogo(cliente, admin):
    codigos = {d["codigo"]: d["nome"] for d in cliente.get("/disciplinas", headers=admin).json()}
    assert codigos.get("COM") == "Comercial"


# ------------------------------------------------------------ correção para todos


def test_obra_nao_perde_o_liberado_quando_sai_revisao_nova(cliente, admin, cenario):
    """Antes, a R01 em andamento tirava o documento inteiro da lista de quem
    não vê trabalho em andamento — com a R00 liberada e valendo em campo."""
    r = cliente.post(
        "/usuarios",
        json={"nome": "Campo", "email": "campo-cm@teste.com.br", "senha": "senha-campo-123"},
        headers=admin,
    )
    cliente.post(
        f"/obras/{cenario['a']['id']}/membros",
        json={"usuario_id": r.json()["id"], "papel": "obra"},
        headers=admin,
    )
    campo = autenticar(cliente, "campo-cm@teste.com.br", "senha-campo-123")

    docs = _codigos(cliente, campo, cenario["a"])
    assert docs["CMA-COM-PE-002"]["revisao_atual"]["numero"] == "00"
    arvore = cliente.get(f"/obras/{cenario['a']['id']}/arvore", headers=campo).json()
    assert arvore["total"] >= 3
