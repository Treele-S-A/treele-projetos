"""Fluxo ponta a ponta: envio, regra de companheiro, liberação e obsolescência."""

import pytest

from .conftest import autenticar, enviar_arquivo

DWG = b"AC1032" + b"\x00" * 200
PDF = b"%PDF-1.7\n" + b"0" * 200
IFC = b"ISO-10303-21;\n" + b"0" * 200


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post(
        "/obras",
        json={"codigo": "TRL001", "nome": "Residencial Aurora", "cliente": "TREELE", "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _documento(cliente, cabecalhos, obra_id, codigo):
    r = cliente.get(
        f"/obras/{obra_id}/documentos", params={"busca": codigo}, headers=cabecalhos
    )
    assert r.status_code == 200, r.text
    for item in r.json()["itens"]:
        if item["codigo"] == codigo:
            return item
    return None


# --------------------------------------------------------------------------
# Nomenclatura barra o envio
# --------------------------------------------------------------------------


def test_nome_fora_do_padrao_e_recusado_antes_de_subir(cliente, admin, obra):
    r = cliente.post(
        f"/obras/{obra['id']}/uploads/iniciar",
        json={"nome_arquivo": "planta forma - REV FINAL (2).dwg", "tamanho": 10},
        headers=admin,
    )
    assert r.status_code == 422
    detalhe = r.json()["detail"]
    assert detalhe["erros"]
    assert detalhe["esperado"]


def test_validacao_previa_lista_erro_por_arquivo(cliente, admin, obra):
    r = cliente.post(
        f"/obras/{obra['id']}/nomenclatura/validar",
        json={
            "nomes": [
                "TRL001-ARQ-PE-001-R00.pdf",
                "TRL001-XYZ-PE-001-R00.pdf",
                "bagunca.dwg",
            ]
        },
        headers=admin,
    )
    assert r.status_code == 200
    resultados = r.json()["resultados"]
    assert resultados[0]["valido"] is True
    assert resultados[0]["disciplina"] == "ARQ"
    assert resultados[0]["revisao"] == "00"
    assert resultados[1]["valido"] is False
    assert resultados[2]["valido"] is False


# --------------------------------------------------------------------------
# Regra de arquivo companheiro
# --------------------------------------------------------------------------


def test_dwg_sozinho_nao_libera_para_obra(cliente, admin, obra):
    r = enviar_arquivo(cliente, admin, obra["id"], "TRL001-EST-PE-001-R00.dwg", DWG)
    assert r.status_code == 200, r.text
    revisao_id = r.json()["revisao"]["id"]

    check = cliente.get(f"/revisoes/{revisao_id}/verificar", headers=admin).json()
    assert check["pode_publicar"] is False
    assert any("PDF" in i for i in check["impedimentos"]), check

    publicar = cliente.post(
        f"/revisoes/{revisao_id}/publicar", json={}, headers=admin
    )
    assert publicar.status_code == 409
    assert publicar.json()["detail"]["erros"]


def test_com_o_pdf_plotado_a_revisao_libera(cliente, admin, obra):
    r = enviar_arquivo(cliente, admin, obra["id"], "TRL001-EST-PE-001-R00.pdf", PDF)
    assert r.status_code == 200, r.text
    revisao_id = r.json()["revisao"]["id"]

    check = cliente.get(f"/revisoes/{revisao_id}/verificar", headers=admin).json()
    assert check["pode_publicar"] is True, check
    assert set(check["tipos_presentes"]) == {"dwg", "pdf"}

    publicar = cliente.post(
        f"/revisoes/{revisao_id}/publicar",
        json={"descricao": "Emissão inicial para obra."},
        headers=admin,
    )
    assert publicar.status_code == 200, publicar.text
    assert publicar.json()["status"] == "liberado_para_obra"
    assert publicar.json()["publicada_em"] is not None


def test_rvt_exige_ifc(cliente, admin, obra):
    r = enviar_arquivo(cliente, admin, obra["id"], "TRL001-ARQ-PE-010-R00.rvt", DWG)
    assert r.status_code == 200, r.text
    revisao_id = r.json()["revisao"]["id"]

    check = cliente.get(f"/revisoes/{revisao_id}/verificar", headers=admin).json()
    assert any("IFC" in i for i in check["impedimentos"]), check

    enviar_arquivo(cliente, admin, obra["id"], "TRL001-ARQ-PE-010-R00.ifc", IFC)
    check = cliente.get(f"/revisoes/{revisao_id}/verificar", headers=admin).json()
    assert check["pode_publicar"] is True, check


# --------------------------------------------------------------------------
# Obsolescência automática
# --------------------------------------------------------------------------


def test_nova_revisao_torna_a_anterior_obsoleta(cliente, admin, obra):
    enviar_arquivo(cliente, admin, obra["id"], "TRL001-EST-PE-001-R01.dwg", DWG,
                   autorizar_com=admin)
    r = enviar_arquivo(cliente, admin, obra["id"], "TRL001-EST-PE-001-R01.pdf", PDF)
    revisao_id = r.json()["revisao"]["id"]

    publicar = cliente.post(
        f"/revisoes/{revisao_id}/publicar",
        json={"descricao": "Ajuste de armadura da viga V12."},
        headers=admin,
    )
    assert publicar.status_code == 200, publicar.text

    documento = _documento(cliente, admin, obra["id"], "TRL001-EST-PE-001")
    assert documento["revisao_atual"]["numero"] == "01"
    assert documento["revisao_atual"]["status"] == "liberado_para_obra"
    assert documento["total_revisoes"] == 2

    detalhe = cliente.get(
        f"/documentos/{documento['id']}", headers=admin
    ).json()
    por_numero = {r["numero"]: r for r in detalhe["revisoes"]}
    assert por_numero["00"]["status"] == "obsoleto"
    assert por_numero["00"]["obsoleta_em"] is not None
    assert por_numero["01"]["status"] == "liberado_para_obra"


def test_revisao_obsoleta_nao_aceita_mais_arquivos(cliente, admin, obra):
    r = enviar_arquivo(cliente, admin, obra["id"], "TRL001-EST-PE-001-R00.ifc", IFC)
    assert r.status_code == 409
    assert "revisão nova" in r.json()["detail"]
    assert "obsoleto" in r.json()["detail"].lower()


def test_revisao_liberada_aceita_arquivo_novo(cliente, admin, obra):
    """Liberar o PDF e mandar o DWG depois — pedido da TREELE em 17/09/2026.

    Acrescentar um formato não altera o que a obra já baixou, então não quebra
    a confiabilidade do histórico.
    """
    r = enviar_arquivo(cliente, admin, obra["id"], "TRL001-ARQ-PL-030-R00.pdf", PDF)
    revisao_id = r.json()["revisao"]["id"]
    assert (
        cliente.post(f"/revisoes/{revisao_id}/publicar", json={}, headers=admin).status_code
        == 200
    )

    depois = enviar_arquivo(cliente, admin, obra["id"], "TRL001-ARQ-PL-030-R00.dwg", DWG)
    assert depois.status_code == 200, depois.text

    revisao = depois.json()["revisao"]
    assert revisao["status"] == "liberado_para_obra"
    assert {a["tipo"] for a in revisao["arquivos"]} == {"pdf", "dwg"}


def test_revisao_liberada_nao_aceita_substituicao(cliente, admin, obra):
    """O que foi liberado não muda: quem já baixou ficaria com outra versão."""
    r = enviar_arquivo(
        cliente, admin, obra["id"], "TRL001-ARQ-PL-030-R00.pdf", PDF, substituir=True
    )
    assert r.status_code == 409
    assert "liberada para obra" in r.json()["detail"]
    assert "revisão nova" in r.json()["detail"].lower()


def test_acrescimo_apos_liberacao_fica_registrado(cliente, admin, obra):
    r = cliente.get(
        f"/obras/{obra['id']}/eventos",
        params={"acao": "upload_iniciado"},
        headers=admin,
    )
    marcados = [
        e for e in r.json()["itens"] if e["detalhes"].get("apos_liberacao") is True
    ]
    assert marcados, "o acréscimo pós-liberação precisa ser auditável"
    assert marcados[0]["detalhes"]["arquivo"].endswith(".dwg")


def test_nao_abre_revisao_nova_com_a_anterior_em_revisao(cliente, admin, obra):
    """Revisão nova só depois da anterior liberada e autorizada (05/10/2026)."""
    enviar_arquivo(cliente, admin, obra["id"], "TRL001-HID-PE-006-R00.pdf", PDF)
    r = enviar_arquivo(cliente, admin, obra["id"], "TRL001-HID-PE-006-R01.pdf", PDF)
    assert r.status_code == 409
    assert "ainda está em revisão" in r.json()["detail"]["erros"][0]


def test_nao_libera_revisao_antiga_depois_da_nova(cliente, admin, obra):
    """Publicar a R00 depois da R01 deixaria a obra com projeto velho.

    Com a autorização de revisão, a R01 nem sobe com a R00 em revisão; mas o
    acervo de antes da regra pode ter esse caso — montado aqui pelo banco.
    """
    from app.db import SessionLocal
    from app.enums import StatusRevisao
    from app.models import Revisao

    r0 = enviar_arquivo(cliente, admin, obra["id"], "TRL001-HID-PE-005-R00.pdf", PDF)
    cliente.post(f"/revisoes/{r0.json()['revisao']['id']}/publicar", json={}, headers=admin)
    r1 = enviar_arquivo(cliente, admin, obra["id"], "TRL001-HID-PE-005-R01.pdf", PDF,
                        autorizar_com=admin)
    with SessionLocal() as db:
        db.get(Revisao, r0.json()["revisao"]["id"]).status = StatusRevisao.em_revisao
        db.commit()
    documento = _documento(cliente, admin, obra["id"], "TRL001-HID-PE-005")
    detalhe = cliente.get(f"/documentos/{documento['id']}", headers=admin).json()
    por_numero = {r["numero"]: r for r in detalhe["revisoes"]}

    assert (
        cliente.post(
            f"/revisoes/{r1.json()['revisao']['id']}/publicar", json={}, headers=admin
        ).status_code
        == 200
    )

    tentativa = cliente.post(
        f"/revisoes/{por_numero['00']['id']}/publicar", json={}, headers=admin
    )
    assert tentativa.status_code == 409
    assert any("mais recente" in e for e in tentativa.json()["detail"]["erros"])


# --------------------------------------------------------------------------
# Download e aviso de obsolescência
# --------------------------------------------------------------------------


def test_download_de_revisao_obsoleta_traz_aviso(cliente, admin, obra):
    documento = _documento(cliente, admin, obra["id"], "TRL001-EST-PE-001")
    detalhe = cliente.get(f"/documentos/{documento['id']}", headers=admin).json()
    obsoleta = next(r for r in detalhe["revisoes"] if r["status"] == "obsoleto")
    arquivo = obsoleta["arquivos"][0]

    r = cliente.get(f"/arquivos/{arquivo['id']}/download", headers=admin)
    assert r.status_code == 200
    assert "OBSOLETA" in r.json()["aviso"]

    from urllib.parse import urlsplit

    partes = urlsplit(r.json()["url"])
    baixado = cliente.get(f"{partes.path}?{partes.query}")
    assert baixado.status_code == 200
    assert baixado.content in (DWG, PDF)


def test_link_de_download_com_assinatura_adulterada_e_recusado(cliente, admin, obra):
    documento = _documento(cliente, admin, obra["id"], "TRL001-EST-PE-001")
    detalhe = cliente.get(f"/documentos/{documento['id']}", headers=admin).json()
    arquivo = detalhe["revisoes"][0]["arquivos"][0]

    r = cliente.get(f"/arquivos/{arquivo['id']}/download", headers=admin)
    from urllib.parse import parse_qs, urlsplit

    partes = urlsplit(r.json()["url"])
    q = parse_qs(partes.query)
    adulterado = (
        f"{partes.path}?chave={q['chave'][0]}&acao=get&exp={q['exp'][0]}"
        "&assinatura=0" * 1
    )
    assert cliente.get(adulterado).status_code == 403


# --------------------------------------------------------------------------
# Permissões
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def projetista(cliente, admin, obra):
    r = cliente.post(
        "/usuarios",
        json={
            "nome": "Projetista Teste",
            "email": "projetista@teste.com.br",
            "senha": "senha-projetista-1",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    usuario = r.json()

    add = cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": usuario["id"], "papel": "projetista"},
        headers=admin,
    )
    assert add.status_code == 201, add.text
    return autenticar(cliente, "projetista@teste.com.br", "senha-projetista-1")


def test_projetista_envia_mas_nao_libera(cliente, projetista, obra):
    r = enviar_arquivo(
        cliente, projetista, obra["id"], "TRL001-ARQ-EP-020-R00.pdf", PDF
    )
    assert r.status_code == 200, r.text
    revisao_id = r.json()["revisao"]["id"]

    check = cliente.get(f"/revisoes/{revisao_id}/verificar", headers=projetista).json()
    assert check["tem_permissao"] is False
    assert check["pode_publicar"] is False

    publicar = cliente.post(
        f"/revisoes/{revisao_id}/publicar", json={}, headers=projetista
    )
    assert publicar.status_code == 403


@pytest.fixture(scope="module")
def pessoal_da_obra(cliente, admin, obra):
    r = cliente.post(
        "/usuarios",
        json={
            "nome": "Encarregado",
            "email": "encarregado@teste.com.br",
            "senha": "senha-encarregado-1",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": r.json()["id"], "papel": "obra"},
        headers=admin,
    )
    return autenticar(cliente, "encarregado@teste.com.br", "senha-encarregado-1")


def test_obra_ve_o_historico_mas_nao_o_que_esta_em_andamento(
    cliente, pessoal_da_obra, admin, obra
):
    """Decisão da TREELE em 22/09/2026.

    A obra precisa do histórico para conferir o que executou semana passada.
    Não precisa — e não deve — ver projeto ainda em elaboração.
    """
    documento = _documento(cliente, admin, obra["id"], "TRL001-EST-PE-001")
    detalhe = cliente.get(
        f"/documentos/{documento['id']}", headers=pessoal_da_obra
    ).json()
    status = {r["status"] for r in detalhe["revisoes"]}
    assert "obsoleto" in status, "a obra precisa enxergar o histórico"
    assert "em_revisao" not in status
    assert "cancelado" not in status


def test_obra_nao_ve_documento_que_nunca_foi_liberado(cliente, pessoal_da_obra, admin, obra):
    """Documento que nunca saiu de 'em revisão' é invisível para a obra."""
    em_andamento = cliente.get(
        f"/obras/{obra['id']}/documentos?por_pagina=200&status_revisao=em_revisao",
        headers=admin,
    ).json()
    assert em_andamento["total"] >= 1, "a base de teste precisa ter algo em revisão"
    codigo = em_andamento["itens"][0]["codigo"]

    da_obra = cliente.get(
        f"/obras/{obra['id']}/documentos?por_pagina=200", headers=pessoal_da_obra
    ).json()
    assert codigo not in {d["codigo"] for d in da_obra["itens"]}


def test_obra_baixa_obsoleto_com_aviso(cliente, pessoal_da_obra, admin, obra):
    documento = _documento(cliente, admin, obra["id"], "TRL001-EST-PE-001")
    completo = cliente.get(f"/documentos/{documento['id']}", headers=admin).json()
    obsoleta = next(r for r in completo["revisoes"] if r["status"] == "obsoleto")

    r = cliente.get(
        f"/arquivos/{obsoleta['arquivos'][0]['id']}/download", headers=pessoal_da_obra
    )
    assert r.status_code == 200, r.text
    # Pode baixar, mas nunca sem saber que está obsoleto.
    assert "OBSOLETA" in r.json()["aviso"]


def test_obra_nao_baixa_o_que_ainda_esta_em_revisao(cliente, pessoal_da_obra, admin, obra):
    pagina = cliente.get(
        f"/obras/{obra['id']}/documentos?por_pagina=200&status_revisao=em_revisao",
        headers=admin,
    ).json()
    documento = pagina["itens"][0]
    detalhe = cliente.get(f"/documentos/{documento['id']}", headers=admin).json()
    em_revisao = next(r for r in detalhe["revisoes"] if r["status"] == "em_revisao")

    r = cliente.get(
        f"/arquivos/{em_revisao['arquivos'][0]['id']}/download", headers=pessoal_da_obra
    )
    assert r.status_code == 403
    assert "não foi liberada" in r.json()["detail"]


def test_arvore_da_obra_esconde_o_que_esta_em_andamento(
    cliente, pessoal_da_obra, admin, obra
):
    completa = cliente.get(f"/obras/{obra['id']}/arvore", headers=admin).json()
    restrita = cliente.get(f"/obras/{obra['id']}/arvore", headers=pessoal_da_obra).json()
    assert restrita["total"] < completa["total"]


# --------------------------------------------------------------------------
# Engenheiro responsável
# --------------------------------------------------------------------------


def test_responsavel_precisa_ser_da_equipe(cliente, admin, obra):
    r = cliente.post(
        "/usuarios",
        json={
            "nome": "De Fora",
            "email": "defora@teste.com.br",
            "senha": "senha-de-fora-12",
        },
        headers=admin,
    )
    de_fora = r.json()["id"]

    recusa = cliente.patch(
        f"/obras/{obra['id']}", json={"responsavel_id": de_fora}, headers=admin
    )
    assert recusa.status_code == 400
    assert "equipe" in recusa.json()["detail"]


def test_define_e_limpa_o_responsavel(cliente, admin, obra):
    membros = cliente.get(f"/obras/{obra['id']}/membros", headers=admin).json()
    alguem = next(m for m in membros if m["papel"] == "projetista")

    r = cliente.patch(
        f"/obras/{obra['id']}",
        json={"responsavel_id": alguem["usuario_id"]},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["responsavel"]["id"] == alguem["usuario_id"]

    # 0 limpa; ausente deixaria como está.
    limpo = cliente.patch(f"/obras/{obra['id']}", json={"responsavel_id": 0}, headers=admin)
    assert limpo.json()["responsavel"] is None


def test_quem_nao_e_da_obra_nao_ve_nada(cliente, admin, obra):
    cliente.post(
        "/usuarios",
        json={
            "nome": "Estranho",
            "email": "estranho@teste.com.br",
            "senha": "senha-estranho-1",
        },
        headers=admin,
    )
    estranho = autenticar(cliente, "estranho@teste.com.br", "senha-estranho-1")

    assert cliente.get("/obras", headers=estranho).json() == []
    assert (
        cliente.get(f"/obras/{obra['id']}/documentos", headers=estranho).status_code
        == 403
    )


def test_sem_token_nao_passa(cliente, obra):
    assert cliente.get(f"/obras/{obra['id']}/documentos").status_code == 401


# --------------------------------------------------------------------------
# Catálogo e auditoria
# --------------------------------------------------------------------------


def test_filtros_do_catalogo(cliente, admin, obra):
    todos = cliente.get(f"/obras/{obra['id']}/documentos", headers=admin).json()
    assert todos["total"] >= 4

    disciplinas = {d["codigo"]: d["id"] for d in cliente.get("/disciplinas", headers=admin).json()}
    so_est = cliente.get(
        f"/obras/{obra['id']}/documentos",
        params={"disciplina_id": disciplinas["EST"]},
        headers=admin,
    ).json()
    assert so_est["total"] >= 1
    assert all(d["disciplina"]["codigo"] == "EST" for d in so_est["itens"])

    so_dwg = cliente.get(
        f"/obras/{obra['id']}/documentos", params={"tipo": "dwg"}, headers=admin
    ).json()
    assert so_dwg["total"] >= 1

    em_revisao = cliente.get(
        f"/obras/{obra['id']}/documentos",
        params={"status_revisao": "em_revisao"},
        headers=admin,
    ).json()
    assert all(
        d["revisao_atual"]["status"] == "em_revisao" for d in em_revisao["itens"]
    )


def test_arvore_agrupa_por_disciplina_fase_e_formato(cliente, admin, obra):
    r = cliente.get(f"/obras/{obra['id']}/arvore", headers=admin)
    assert r.status_code == 200, r.text
    a = r.json()

    assert a["obra_codigo"] == "TRL001"
    assert a["total"] > 0 and a["tamanho"] > 0

    # O total de cada nível é a soma do que está abaixo dele.
    assert a["total"] == sum(d["total"] for d in a["disciplinas"])
    assert a["tamanho"] == sum(d["tamanho"] for d in a["disciplinas"])
    for d in a["disciplinas"]:
        assert d["total"] == sum(f["total"] for f in d["fases"])
        assert d["tamanho"] == sum(f["tamanho"] for f in d["fases"])
        for f in d["fases"]:
            assert f["total"] == sum(tp["total"] for tp in f["tipos"])
            assert f["tamanho"] == sum(tp["tamanho"] for tp in f["tipos"])

    est = next(d for d in a["disciplinas"] if d["codigo"] == "EST")
    pe = next(f for f in est["fases"] if f["codigo"] == "PE")
    assert {tp["tipo"] for tp in pe["tipos"]} >= {"dwg", "pdf"}


def test_arvore_nao_carrega_a_lista_de_arquivos(cliente, admin, obra):
    """A árvore navega; quem lista arquivo é a pasta. Mandar todos os nomes
    aqui seriam megabytes de JSON que nenhuma tela desenha."""
    a = cliente.get(f"/obras/{obra['id']}/arvore", headers=admin).json()
    tipo = a["disciplinas"][0]["fases"][0]["tipos"][0]
    assert "arquivos" not in tipo
    assert tipo["total"] >= 1


def test_arvore_conta_so_a_revisao_vigente(cliente, admin, obra):
    """TRL001-EST-PE-001 tem R00 (obsoleta) e R01. Só a R01 conta no acervo."""
    vigente = cliente.get(f"/obras/{obra['id']}/arvore", headers=admin).json()
    todas = cliente.get(
        f"/obras/{obra['id']}/arvore", params={"todas_revisoes": "true"}, headers=admin
    ).json()
    assert todas["total"] > vigente["total"]


# --------------------------------------------------------------------------
# Conteúdo da pasta
# --------------------------------------------------------------------------


def test_pasta_traz_documentos_com_historico_completo(cliente, admin, obra):
    r = cliente.get(f"/obras/{obra['id']}/pastas/EST/PE", headers=admin)
    assert r.status_code == 200, r.text
    pasta = r.json()

    assert pasta["disciplina"] == {"codigo": "EST", "nome": "Estrutura"}
    assert pasta["fase"]["codigo"] == "PE"
    assert pasta["total"] == len(pasta["documentos"]) >= 1

    doc = next(d for d in pasta["documentos"] if d["codigo"] == "TRL001-EST-PE-001")
    numeros = [r["numero"] for r in doc["revisoes"]]
    assert numeros == ["01", "00"], "mais recente no topo"
    assert doc["revisao_atual"]["numero"] == "01"

    por_numero = {r["numero"]: r for r in doc["revisoes"]}
    assert por_numero["00"]["status"] == "obsoleto"
    assert por_numero["01"]["status"] == "liberado_para_obra"
    # Cada revisão traz os próprios arquivos.
    assert {a["tipo"] for a in por_numero["01"]["arquivos"]} == {"dwg", "pdf"}


def test_pasta_inexistente_responde_404(cliente, admin, obra):
    assert cliente.get(f"/obras/{obra['id']}/pastas/ZZZ/PE", headers=admin).status_code == 404
    assert cliente.get(f"/obras/{obra['id']}/pastas/EST/ZZ", headers=admin).status_code == 404


def test_pasta_aceita_codigo_em_caixa_baixa(cliente, admin, obra):
    r = cliente.get(f"/obras/{obra['id']}/pastas/est/pe", headers=admin)
    assert r.status_code == 200
    assert r.json()["disciplina"]["codigo"] == "EST"


def test_pasta_vazia_responde_lista_vazia(cliente, admin, obra):
    r = cliente.get(f"/obras/{obra['id']}/pastas/PAI/AB", headers=admin)
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["documentos"] == []


def test_lista_mestra_em_csv(cliente, admin, obra):
    r = cliente.get(f"/obras/{obra['id']}/documentos/exportar", headers=admin)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    texto = r.content.decode("utf-8-sig")
    assert "Código;Título;Disciplina" in texto
    assert "TRL001-EST-PE-001" in texto


def test_auditoria_registra_download_e_publicacao(cliente, admin, obra):
    r = cliente.get(f"/obras/{obra['id']}/eventos", headers=admin)
    assert r.status_code == 200
    acoes = {e["acao"] for e in r.json()["itens"]}
    assert "download" in acoes
    assert "revisao_publicada" in acoes
    assert "upload_concluido" in acoes

    downloads = cliente.get(
        f"/obras/{obra['id']}/eventos", params={"acao": "download"}, headers=admin
    ).json()
    assert downloads["total"] >= 1
    # Procura o evento em vez de supor a ordem: qualquer pessoa da obra baixando
    # mudaria quem está no topo da lista.
    evento = next(
        e for e in downloads["itens"] if e["usuario"]["email"] == "admin@teste.com.br"
    )
    assert evento["detalhes"]["documento"]


def test_projetista_nao_ve_auditoria(cliente, projetista, obra):
    assert (
        cliente.get(f"/obras/{obra['id']}/eventos", headers=projetista).status_code
        == 403
    )


def test_responsavel_pode_ter_qualquer_papel(cliente, admin, obra, pessoal_da_obra):
    """O engenheiro responsável costuma estar na obra, não na equipe de
    projetos: o papel dele na equipe não restringe quem pode ser escolhido."""
    membros = cliente.get(f"/obras/{obra['id']}/membros", headers=admin).json()
    da_obra = next(m for m in membros if m["papel"] == "obra")

    r = cliente.patch(
        f"/obras/{obra['id']}", json={"responsavel_id": da_obra["usuario_id"]}, headers=admin
    )

    assert r.status_code == 200, r.text
    assert r.json()["responsavel"]["id"] == da_obra["usuario_id"]
    cliente.patch(f"/obras/{obra['id']}", json={"responsavel_id": 0}, headers=admin)
