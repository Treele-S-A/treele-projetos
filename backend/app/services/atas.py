"""Ata de análise crítica: o checklist PRO-FL-005 respondido antes de liberar
para obra (TREELE, 29/10/2026), para atender o SIAC.

O checklist sai da planilha da Treèle (`checklist_pro_fl_005.json`, gerado da
PRO-FL-005 rev. 02). A planilha é dividida pelo projeto analisado; a disciplina
da revisão escolhe o bloco, e os itens de representação gráfica (RGF) entram
sempre. As colunas de fase (estudo preliminar, executivo) e de quem confere
ficam de fora: a ata é respondida uma vez por revisão.

Regras:
- toda pergunta tem resposta: S, N ou N/A;
- "N" pede comentário, e qualquer "N" faz a ata "não conforme": ela fica
  registrada e as revisões dela não podem ser liberadas (reprovar, ou refazer a
  análise);
- uma revisão com ata conforme não ganha outra.
"""

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AtaAnalise, Revisao, Usuario

RESPOSTAS = {"S", "N", "NA"}

# "Análise crítica de projeto arquitetônico": o modelo ENG-FL-001 é o da
# arquitetura; as outras disciplinas entram no mesmo título.
ADJETIVOS = {
    "ARQ": "arquitetônico", "EST": "estrutural", "FUN": "de fundação", "CON": "de contenção",
    "HID": "hidrossanitário", "DRE": "de drenagem", "ELE": "elétrico", "INC": "de incêndio",
    "GAS": "de gás", "CLI": "de climatização", "TEL": "de telecomunicações", "PAI": "paisagístico",
    "IMP": "de impermeabilização", "ESQ": "de esquadrias", "TOP": "topográfico",
    "CTL": "de conforto térmico e lumínico", "LUM": "luminotécnico", "SPD": "de SPDA",
    "INT": "de interiores",
}


def adjetivo(codigo: str, nome: str) -> str:
    return ADJETIVOS.get(codigo.upper(), f"de {nome.lower()}")


@lru_cache
def checklist() -> dict:
    return json.loads((Path(__file__).parent / "checklist_pro_fl_005.json").read_text(encoding="utf-8"))


def formulario_da_disciplina(codigo: str) -> dict:
    """O formulário de uma disciplina: título, blocos usados e os itens em
    grupos (o primeiro é sempre a representação gráfica)."""
    c = checklist()
    blocos = [c["blocos"][b] for b in c["disciplinas"].get(codigo.upper(), [])]
    grupos: list[dict] = [{"titulo": "Representação gráfica", "itens": c["rgf"]}]
    for bloco in blocos:
        for item in bloco["itens"]:
            titulo = item["grupo"] if len(blocos) == 1 else f"{bloco['nome']} · {item['grupo']}"
            if grupos[-1]["titulo"] != titulo:
                grupos.append({"titulo": titulo, "itens": []})
            grupos[-1]["itens"].append(item)
    nomes = " + ".join(b["nome"] for b in blocos) or "só representação gráfica"
    return {
        "formulario": f"{c['formulario']} rev. {c['revisao']} · {nomes}",
        "titulo": c["titulo"],
        "blocos": [b["nome"] for b in blocos],
        "grupos": grupos,
    }


def impedimento(revisao: Revisao) -> str | None:
    """O que a ata ainda impede na liberação desta revisão, ou None."""
    if not settings.ata_analise_obrigatoria:
        return None
    ata = revisao.ata
    if ata is None:
        return "Falta a ata de análise crítica (checklist PRO-FL-005) desta revisão."
    if ata.resultado != "conforme":
        return (
            f"A {ata.codigo} registrou itens não conformes. Reprove a revisão ou "
            "refaça a análise crítica."
        )
    return None


def precisa_de_ata(revisao: Revisao) -> bool:
    return settings.ata_analise_obrigatoria and (revisao.ata is None or revisao.ata.resultado != "conforme")


class AtaInvalida(ValueError):
    def __init__(self, mensagem: str, erros: list[str] | None = None):
        super().__init__(mensagem)
        self.erros = erros or []


def criar(
    db: Session,
    revisoes: list[Revisao],
    usuario: Usuario,
    respostas: dict[str, tuple[str, str]],
    observacoes: str | None,
) -> AtaAnalise:
    """Registra a ata das revisões (mesma obra e disciplina, já conferidas por
    quem chama). `respostas`: id do item → (resposta, comentário)."""
    documento = revisoes[0].documento
    formulario = formulario_da_disciplina(documento.disciplina.codigo)
    itens, erros = [], []
    for grupo in formulario["grupos"]:
        for item in grupo["itens"]:
            resposta, comentario = respostas.get(item["id"], ("", ""))
            resposta = (resposta or "").strip().upper().replace("/", "")
            comentario = (comentario or "").strip()
            if resposta not in RESPOSTAS:
                erros.append(f"Item {item['item']} sem resposta.")
            elif resposta == "N" and not comentario:
                erros.append(f"Item {item['item']} marcado N: diga no comentário o que não está conforme.")
            itens.append({**item, "grupo": grupo["titulo"], "resposta": resposta, "comentario": comentario or None})
    if erros:
        raise AtaInvalida("O checklist não está completo.", erros)

    numero = (db.scalar(select(func.max(AtaAnalise.numero)).where(AtaAnalise.obra_id == documento.obra_id)) or 0) + 1
    ata = AtaAnalise(
        obra_id=documento.obra_id,
        disciplina_id=documento.disciplina_id,
        numero=numero,
        resultado="nao_conforme" if any(i["resposta"] == "N" for i in itens) else "conforme",
        formulario=formulario["formulario"],
        itens=itens,
        observacoes=(observacoes or "").strip() or None,
        revisoes_texto=[
            {"id": r.id, "documento": r.documento.codigo, "titulo": r.documento.titulo, "revisao": r.numero}
            for r in revisoes
        ],
        criada_por_id=usuario.id,
    )
    ata.revisoes = list(revisoes)
    db.add(ata)
    db.flush()
    for r in revisoes:
        db.expire(r, ["atas"])
    return ata
