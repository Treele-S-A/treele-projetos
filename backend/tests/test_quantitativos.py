"""Quantitativos dos modelos IFC no chat (TREELE, 21/10/2026): a consulta soma
o resumo guardado ao lado do IFC, pelo material ou pelo tipo, com as regras de
quem pode ver o arquivo."""

import json

import pytest
from sqlalchemy import select

from app.api.arquivos import chave_resumo
from app.db import SessionLocal
from app.models import Arquivo, Usuario
from app.services.chat_ferramentas import Ferramentas, descrever
from app.services.storage import armazenamento

from .conftest import autenticar, enviar_arquivo

SENHA = "senha-quant-12345"
IFC = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n" + b" " * 300
PDF = b"%PDF-1.7\n" + b"0" * 200

RESUMO = {
    "versao": 1,
    "elementos": 6,
    "grandezas": {"NetSideArea": "area", "NetVolume": "volume", "Length": "comprimento", "Width": "comprimento"},
    "pavimentos": ["1° Pav", "Pav Tipo"],
    "materiais": {
        "AC_Pintura Branca Interna - 1,5": [".Pintura Branca Interna (0.2 cm)", ".Reboco Interno (1.3 cm)"],
        "AC_Pintura Branco Externa - 2,0": [".Pintura Branca Externa (0.2 cm)", ".Reboco Externo (1.8 cm)"],
        "AC_Cerâmica branca interna": [".Cerâmica (0.4 cm)", ".Argamassa (0.6 cm)"],
        "Porta 80x210": ["Madeira"],
    },
    "grupos": [
        {"categoria": "Parede", "tipo": "AC_Pintura Branca Interna - 1,5", "pavimento": "1° Pav", "n": 2,
         "q": {"NetSideArea": 10.5, "NetVolume": 0.15, "Length": 7.0, "Width": 0.03}},
        {"categoria": "Parede", "tipo": "AC_Pintura Branca Interna - 1,5", "pavimento": "Pav Tipo", "n": 1,
         "q": {"NetSideArea": 4.5, "NetVolume": 0.06, "Length": 3.0, "Width": 0.015}},
        {"categoria": "Parede", "tipo": "AC_Pintura Branco Externa - 2,0", "pavimento": "Pav Tipo", "n": 1,
         "q": {"NetSideArea": 20.0}},
        {"categoria": "Parede", "tipo": "AC_Cerâmica branca interna", "pavimento": "1° Pav", "n": 1,
         "q": {"NetSideArea": 8.0}},
        {"categoria": "Porta", "tipo": "Porta 80x210", "pavimento": "1° Pav", "n": 1, "q": {}},
    ],
}


def _pessoa(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@quant.teste.com.br"
    u = cliente.post("/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA},
                     headers=admin).json()
    cliente.post(f"/obras/{obra['id']}/membros", json={"usuario_id": u["id"], "papel": papel}, headers=admin)
    autenticar(cliente, email, SENHA)
    return u["id"]


@pytest.fixture(scope="module")
def c(cliente, admin):
    obra = cliente.post("/obras", json={"codigo": "QTD", "nome": "Obra quantitativos"}, headers=admin).json()
    coord = _pessoa(cliente, admin, obra, "coordqtd", "coordenador")
    campo = _pessoa(cliente, admin, obra, "campoqtd", "obra")
    arq = enviar_arquivo(cliente, admin, obra["id"], "QTD-ARQ-PE-MOD-R00.ifc", IFC).json()
    enviar_arquivo(cliente, admin, obra["id"], "QTD-ARQ-PE-MOD-R00.pdf", PDF)
    cliente.post(f"/revisoes/{arq['revisao']['id']}/publicar", json={"avisar": False}, headers=admin)
    hid = enviar_arquivo(cliente, admin, obra["id"], "QTD-HID-PE-MOD-R00.ifc", IFC).json()  # em análise
    db = SessionLocal()
    try:
        a = db.get(Arquivo, arq["arquivo"]["id"])
        armazenamento.gravar_bytes(chave_resumo(a), json.dumps(RESUMO).encode(), "application/json")
    finally:
        db.close()
    return {"obra": obra, "coord": coord, "campo": campo, "hid": hid["arquivo"]["id"]}


def _ferramentas(usuario_id):
    db = SessionLocal()
    return Ferramentas(db, db.get(Usuario, usuario_id))


def test_reboco_soma_os_tipos_com_reboco_nas_camadas(c):
    r = _ferramentas(c["coord"]).executar("quantitativos_modelo", {"obra": "QTD", "busca": "reboco"})
    arq = next(m for m in r["modelos"] if m["documento"] == "QTD-ARQ-PE-MOD")
    assert arq["revisao"] == "R00" and arq["encontrados"] == 2
    assert arq["total"]["area_lateral_liquida_m2"] == 35.0  # 10,5 + 4,5 + 20
    interno = next(t for t in arq["tipos"] if "Interna" in t["tipo"])
    assert interno["elementos"] == 3 and interno["quantidades"]["area_lateral_liquida_m2"] == 15.0
    assert interno["quantidades"]["comprimento_m"] == 10.0
    assert "Width" not in json.dumps(interno)  # largura somada não entra
    assert arq["por_pavimento"]["Pav Tipo"]["area_lateral_liquida_m2"] == 24.5
    # O HID em análise não tem resumo: aparece avisando, sem número.
    hid = next(m for m in r["modelos"] if m["documento"] == "QTD-HID-PE-MOD")
    assert "ainda não tem resumo" in hid["erro"]


def test_busca_sem_acento_varias_palavras_e_pavimento(c):
    f = _ferramentas(c["coord"])
    r = f.executar("quantitativos_modelo", {"obra": "QTD", "busca": "ceramica argamassa", "disciplina": "ARQ"})
    assert [t["tipo"] for t in r["modelos"][0]["tipos"]] == ["AC_Cerâmica branca interna"]
    r = f.executar("quantitativos_modelo", {"obra": "QTD", "busca": "reboco", "pavimento": "tipo"})
    arq = r["modelos"][0]
    assert arq["total"]["area_lateral_liquida_m2"] == 24.5


def test_sem_busca_mostra_o_que_o_modelo_tem(c):
    r = _ferramentas(c["coord"]).executar("quantitativos_modelo", {"obra": "QTD", "disciplina": "ARQ"})
    arq = r["modelos"][0]
    assert arq["categorias"] == {"Parede": 5, "Porta": 1}
    assert ".Reboco Interno" in arq["materiais"] and "1° Pav" in arq["pavimentos"]


def test_obra_so_consulta_o_que_pode_abrir(c):
    r = _ferramentas(c["campo"]).executar("quantitativos_modelo", {"obra": "QTD", "busca": "reboco"})
    assert [m["documento"] for m in r["modelos"]] == ["QTD-ARQ-PE-MOD"]  # o HID em análise não aparece


def test_nada_encontrado_e_etapa_na_tela(c):
    r = _ferramentas(c["coord"]).executar("quantitativos_modelo", {"obra": "QTD", "busca": "granito", "disciplina": "ARQ"})
    assert r["modelos"][0]["encontrados"] == 0
    assert descrever("quantitativos_modelo", {"obra": "SER", "busca": "reboco"}) == (
        "Somando quantidades do modelo IFC (reboco) na obra SER"
    )


# ------------------------------------------------------- índice completo

INDICE = {
    "versao": 1,
    "categorias": ["Porta", "Parede"],
    "tipos": ["Porta_Abrir_1F:80x210", "Porta_Abrir_1F:90x210", "AC_Pintura Branca Interna - 1,5"],
    "pavimentos": ["1° Pav", "Pav Tipo"],
    "campos": ["Atributos/Classe IFC", "Pset_DoorCommon/IsExternal", "Cotas/Área",
               "Dados de identidade/Marca", "Tipo · Pset_DoorCommon/FireRating"],
    "elementos": [
        [0, 0, 0, "g1", "Porta 1", {"0": "IFCDOOR", "1": "Sim", "2": 1.68, "3": "P1", "4": "P-60"}],
        [0, 0, 1, "g2", "Porta 2", {"0": "IFCDOOR", "1": "Não", "2": 1.68, "3": "P2"}],
        [0, 1, 1, "g3", "Porta 3", {"0": "IFCDOOR", "1": "Sim", "2": 1.89, "3": "P3", "4": "P-90"}],
        [1, 2, 0, "g4", "Parede 1", {"0": "IFCWALLSTANDARDCASE", "2": 7.75}],
    ],
}


@pytest.fixture(scope="module")
def com_indice(c):
    import gzip

    from app.api.arquivos import chave_indice

    db = SessionLocal()
    try:
        a = db.scalars(select(Arquivo).where(Arquivo.nome_original == "QTD-ARQ-PE-MOD-R00.ifc")).one()
        armazenamento.gravar_bytes(chave_indice(a), gzip.compress(json.dumps(INDICE).encode()), "application/gzip")
    finally:
        db.close()
    return c


def _elementos(c, **args):
    r = _ferramentas(c["coord"]).executar("consultar_elementos", {"obra": "QTD", "disciplina": "ARQ", **args})
    return r["modelos"][0]


def test_filtra_por_parametro_e_agrupa(com_indice):
    m = _elementos(com_indice, categoria="porta", filtros=[{"campo": "IsExternal", "operador": "igual", "valor": "sim"}],
                   agrupar_por="pavimento", somar="Cotas/Área")
    assert m["encontrados"] == 2
    assert m["somado"]["total"] == 3.57 and m["somado"]["campo"] == "Cotas/Área"
    assert {g["valor"]: g["elementos"] for g in m["grupos"]} == {"1° Pav": 1, "Pav Tipo": 1}


def test_parametro_do_tipo_preenchido_e_maior(com_indice):
    m = _elementos(com_indice, categoria="IfcDoor", filtros=[{"campo": "fireRating", "operador": "preenchido"}],
                   listar=True)
    assert [e["nome"] for e in m["elementos"]] == ["Porta 1", "Porta 3"]
    assert m["elementos"][1]["Tipo · Pset_DoorCommon/FireRating"] == "P-90"
    m = _elementos(com_indice, filtros=[{"campo": "Área", "operador": "maior", "valor": "1.7"}])
    assert m["encontrados"] == 2  # a porta de 1,89 e a parede


def test_mostrar_campos_e_campo_inexistente(com_indice):
    m = _elementos(com_indice, categoria="porta", mostrar_campos=True)
    nomes = {x["campo"]: x for x in m["campos"]}
    assert nomes["Dados de identidade/Marca"]["preenchido_em"] == 3
    assert nomes["Pset_DoorCommon/IsExternal"]["exemplos"] == ["Não", "Sim"]
    m = _elementos(com_indice, filtros=[{"campo": "fck", "valor": "40"}])
    assert m["encontrados"] == 0 and "mostrar_campos" in m["aviso"]


def test_sem_indice_avisa(com_indice):
    r = _ferramentas(com_indice["coord"]).executar("consultar_elementos", {"obra": "QTD", "categoria": "porta"})
    hid = next(m for m in r["modelos"] if m["documento"] == "QTD-HID-PE-MOD")
    assert "ainda não tem índice" in hid["erro"]


def test_agrupa_por_combinacao(com_indice):
    m = _elementos(com_indice, categoria="porta", agrupar_por="pavimento, tipo")
    assert m["agrupado_por"] == "pavimento · tipo"
    assert {g["valor"]: g["elementos"] for g in m["grupos"]} == {
        "1° Pav · Porta_Abrir_1F:80x210": 1,
        "Pav Tipo · Porta_Abrir_1F:80x210": 1,
        "Pav Tipo · Porta_Abrir_1F:90x210": 1,
    }
