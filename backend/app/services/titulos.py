"""Título do documento: obrigatório, e limpo do mesmo jeito em todo lugar.

O título não vem no nome do arquivo (decisão da TREELE, 17/09/2026), mas é por
ele que a equipe acha a prancha na lista e na pasta — ninguém procura
"MIL-ELE-PE-001", procura "Pontos Elétricos Pav. Tipo". Por isso ele é pedido
na primeira vez que o documento aparece (TREELE, 25/09/2026) e, dali em
diante, reaproveitado em todas as revisões.

A regra mora no servidor, não na tela: validação só na interface seria
decorativa — qualquer um chamaria a API direto e criaria documento sem título.
"""

import re

TITULO_MIN = 3
TITULO_MAX = 300


def limpar_titulo(valor: str | None) -> str | None:
    """Espaços repetidos viram um só; vazio vira None."""
    if valor is None:
        return None
    limpo = re.sub(r"\s+", " ", valor).strip()
    return limpo or None


def problema_no_titulo(titulo: str | None) -> str | None:
    """O que está errado com o título, em linguagem de quem usa; None se nada."""
    if not titulo:
        return "Informe o título do documento."
    if len(titulo) < TITULO_MIN:
        return f"O título precisa ter ao menos {TITULO_MIN} caracteres."
    if len(titulo) > TITULO_MAX:
        return f"O título pode ter no máximo {TITULO_MAX} caracteres."
    return None
