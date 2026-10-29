"""Gera app/services/checklist_pro_fl_005.json a partir da planilha
PRO-FL-005 (Revisão 02). Precisa do openpyxl (só para isto, fora do requirements):

    pip install openpyxl
    python scripts/gerar_checklist_pro_fl_005.py PRO-FL-005.xlsx app/services/checklist_pro_fl_005.json

Planilha nova (Revisão 03): confira as faixas de linhas em BLOCOS e o número da
revisão em `saida`, gere e rode os testes (tests/test_atas.py).

A planilha é dividida pelo projeto analisado (cada bloco recomeça em "1.1 RGF");
dentro de um bloco, a coluna DISC diz com que disciplina o item compatibiliza.
Os requisitos de desempenho (rev. 02, linhas 422-447) vêm por disciplina e vão
para o bloco da disciplina."""

import json
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import openpyxl  # noqa: E402

ROTULOS = {
    "RGF": "Representação gráfica", "SOND": "Sondagem", "PLAN": "Planialtimétrico",
    "ARQ": "Arquitetura", "EST": "Estrutura", "ELE": "Elétrica", "HID": "Hidráulica",
    "VED": "Vedação", "AC": "Ar-condicionado", "EXA": "Exaustão", "ELEV": "Elevadores",
    "PRES": "Pressurização", "PAIS": "Paisagismo", "INC": "Incêndio", "FUND": "Fundação",
    "DES": "Desempenho",
}
DESEMPENHO_DESDE = 422  # requisitos de desempenho por disciplina (NBR 15575)

# Bloco: (nome, faixas de linhas da planilha). Os RGF de cada bloco vão para a
# lista comum, que aparece em todas as disciplinas.
BLOCOS = {
    "SOND": ("Sondagem", [(12, 28)]),
    "TOP": ("Levantamento planialtimétrico", [(29, 47)]),
    "ARQ": ("Arquitetura", [(48, 166), (432, 442)]),
    "EST": ("Estrutura", [(167, 262), (422, 428)]),
    "HID": ("Hidráulica", [(263, 327), (443, 447)]),
    "ELE": ("Elétrica", [(328, 394)]),
    "FUN": ("Fundação", [(395, 416), (429, 431)]),
    "DES": ("Simulações de desempenho", [(417, 421)]),
}
# Disciplina do sistema → blocos da planilha.
DISCIPLINAS = {
    "ARQ": ["ARQ"], "EST": ["EST"], "HID": ["HID"], "ELE": ["ELE"],
    "FUN": ["SOND", "FUN"], "TOP": ["TOP"], "CTL": ["DES"],
}


def texto(v) -> str:
    linhas = [re.sub(r"[ \t]+", " ", x).strip() for x in str(v).replace("\r", "").split("\n")]
    return "\n".join(x for x in linhas if x)


ws = openpyxl.load_workbook(sys.argv[1], data_only=True).worksheets[0]
rgf, vistos = [], set()
blocos = {}
for chave, (nome, faixas) in BLOCOS.items():
    itens = []
    anterior = None
    for ini, fim in faixas:
        for r in range(ini, fim + 1):
            a, b, c = (ws.cell(r, k).value for k in (1, 2, 3))
            if not c:
                continue
            t = texto(c)
            if b is None and a is None:  # linha 177: continuação sem número, do item de cima
                a, b = f"{anterior['item']}b", anterior["disc"]
            a, b = str(a).strip(), str(b).strip()
            if b == "RGF":
                if t not in vistos:
                    vistos.add(t)
                    rgf.append({"id": f"l{r}", "item": f"1.{len(rgf) + 1}", "disc": "RGF", "texto": t})
                continue
            grupo = "Desempenho (NBR 15575)" if r >= DESEMPENHO_DESDE else ROTULOS.get(b, b)
            anterior = {"id": f"l{r}", "item": a, "disc": b, "grupo": grupo, "texto": t}
            itens.append(anterior)
    blocos[chave] = {"nome": nome, "itens": itens}

saida = {
    "formulario": "PRO-FL-005",
    "titulo": "Checklist de Verificação e Análise Crítica de Projetos",
    "revisao": "02",
    "data": "06/08/2026",
    "rgf": rgf,
    "blocos": blocos,
    "disciplinas": DISCIPLINAS,
}
Path(sys.argv[2]).write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
print("RGF", len(rgf), {k: len(v["itens"]) for k, v in blocos.items()})
