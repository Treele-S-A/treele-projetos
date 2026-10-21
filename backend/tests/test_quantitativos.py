"""Quantitativos dos modelos IFC no chat (TREELE, 21/10/2026): a consulta soma
o resumo guardado ao lado do IFC, pelo material ou pelo tipo, com as regras de
quem pode ver o arquivo."""

import json

import pytest

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
