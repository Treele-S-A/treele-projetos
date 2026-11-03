"""Cronograma de projetos em Gantt — PRO-FL-001 (TREELE, 03/11/2026).

As datas saem do cálculo, não do que está guardado: o início do projeto, a
duração de cada atividade em dias úteis (segunda a sexta), as predecessoras
e, se a pessoa arrastou a barra, o "não iniciar antes de" (inicio_fixo).

Vínculos, como no macrofluxo do Vivere Due:
- TI (término-início): a sucessora começa depois que a predecessora termina;
- II (início-início): a sucessora começa junto (ou depois) do início dela;
- TT (término-término): a sucessora termina junto (ou depois) do fim dela.
A defasagem soma dias úteis (negativa, adianta).

Ida (datas mais cedo) e volta (datas mais tarde) dão a folga de cada
atividade; folga zero é o caminho crítico — o que atrasa o fim do projeto.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from ..models import Cronograma, CronogramaAtividade

TIPOS = ("TI", "II", "TT")
_SEGUNDA = date(2000, 1, 3)  # uma segunda-feira qualquer: a régua dos dias úteis


def indice(d: date) -> int:
    """O dia útil de d (sábado e domingo contam como a segunda seguinte)."""
    dias = (d - _SEGUNDA).days
    semanas, resto = divmod(dias, 7)
    return semanas * 5 + min(resto, 5)


def data(i: int) -> date:
    semanas, resto = divmod(i, 5)
    return _SEGUNDA + timedelta(days=semanas * 7 + resto)


@dataclass
class Calculo:
    inicio: date
    termino: date
    folga: int
    critica: bool


class CicloNoCronograma(ValueError):
    pass


def _ordem_topologica(atividades: list[CronogramaAtividade]) -> list[CronogramaAtividade]:
    por_id = {a.id: a for a in atividades}
    faltam = {a.id: sum(1 for v in a.predecessoras if v.predecessora_id in por_id) for a in atividades}
    sucessoras: dict[int, list[int]] = {a.id: [] for a in atividades}
    for a in atividades:
        for v in a.predecessoras:
            if v.predecessora_id in por_id:
                sucessoras[v.predecessora_id].append(a.id)
    fila = [a.id for a in atividades if faltam[a.id] == 0]
    saida: list[CronogramaAtividade] = []
    while fila:
        i = fila.pop(0)
        saida.append(por_id[i])
        for s in sucessoras[i]:
            faltam[s] -= 1
            if faltam[s] == 0:
                fila.append(s)
    if len(saida) != len(atividades):
        raise CicloNoCronograma("As predecessoras formam um ciclo.")
    return saida


def calcular(cronograma: Cronograma) -> dict[int, Calculo]:
    """Início, término, folga e caminho crítico de cada atividade."""
    atividades = list(cronograma.atividades)
    if not atividades:
        return {}
    ordem = _ordem_topologica(atividades)
    base = indice(cronograma.inicio)
    cedo: dict[int, int] = {}  # índice do primeiro dia útil
    dur = {a.id: max(0, a.duracao) for a in atividades}
    for a in ordem:
        s = base
        if a.inicio_fixo:
            s = max(s, indice(a.inicio_fixo))
        for v in a.predecessoras:
            p = v.predecessora_id
            if p not in cedo:
                continue
            fim_p = cedo[p] + dur[p]  # exclusivo
            if v.tipo == "II":
                s = max(s, cedo[p] + v.defasagem)
            elif v.tipo == "TT":
                s = max(s, fim_p + v.defasagem - dur[a.id])
            else:
                s = max(s, fim_p + v.defasagem)
        cedo[a.id] = s
    fim_projeto = max(cedo[i] + dur[i] for i in cedo)
    # Volta: o fim mais tarde de cada uma sem atrasar o projeto.
    tarde_fim: dict[int, int] = {i: fim_projeto for i in cedo}
    for a in reversed(ordem):
        for v in a.predecessoras:
            p = v.predecessora_id
            if p not in cedo:
                continue
            ls = tarde_fim[a.id] - dur[a.id]
            if v.tipo == "II":
                limite = ls - v.defasagem + dur[p]
            elif v.tipo == "TT":
                limite = tarde_fim[a.id] - v.defasagem
            else:
                limite = ls - v.defasagem
            tarde_fim[p] = min(tarde_fim[p], limite)
    saida: dict[int, Calculo] = {}
    for i, s in cedo.items():
        folga = tarde_fim[i] - (s + dur[i])
        saida[i] = Calculo(
            inicio=data(s),
            termino=data(s + dur[i] - 1) if dur[i] > 0 else data(s),
            folga=folga,
            critica=folga <= 0,
        )
    return saida


def gera_ciclo(atividades: list[CronogramaAtividade], sucessora_id: int, predecessoras: list[int]) -> bool:
    """Se a sucessora passar a depender dessas predecessoras, fecha um ciclo?"""
    preds = {a.id: [v.predecessora_id for v in a.predecessoras] for a in atividades}
    preds[sucessora_id] = list(predecessoras)
    vistos: set[int] = set()
    pilha = list(predecessoras)
    while pilha:
        i = pilha.pop()
        if i == sucessora_id:
            return True
        if i in vistos:
            continue
        vistos.add(i)
        pilha.extend(preds.get(i, []))
    return False


# ----------------------------------------------------------------- o modelo
# As atividades do cronograma novo, compiladas de duas planilhas (03/11/2026):
# - PRO-FL-001 (Cronograma técnico de contratação e desenvolvimento de
#   projetos): as fases Preliminares, Projetos, Laudos e estudos e PCP, e os
#   responsáveis já preenchidos;
# - Macrofluxo do Vivere Due (Cockpit Novos Negócios e Incorporação): as
#   seções e as predecessoras de cada atividade, TI e o único II (gás com o
#   ante-projeto de incêndio).
# O que só uma das duas tinha entrou uma vez; o que as duas tinham com nomes
# diferentes virou uma linha só (ensaio de ruído = análise de entorno de
# ruído; simulação de desempenho = termo-lumínica + acústica). As atividades
# da Incorporação e do PCP que o macrofluxo usa como predecessoras entram
# também, senão os vínculos ficam soltos. Acrescentados os vínculos óbvios
# que o macrofluxo não trazia: as análises da CEF em sequência (1ª → 2ª →
# 3ª), os projetos executivos a partir da arquitetura (II com defasagem: a
# estrutura começa 10 dias úteis depois do arquitetônico, não no fim dele) e
# a compatibilização depois de todos os executivos. Durações em dias úteis,
# estimadas: nenhuma das planilhas traz duração (as datas do macrofluxo são
# quase todas de um dia só). Cada coordenador ajusta na obra dele.
#
# (chave, nome, área, responsável, duração, [(predecessora, tipo, defasagem)])
MODELO: list[tuple[str, list[tuple[str, str, str | None, str | None, int, list[tuple[str, str, int]]]]]] = [
    ("Abertura do projeto", [
        ("passagem", "Reunião de passagem (Incorporação → Projetos)", "Incorporação", None, 0, []),
        ("spe", "Abrir SPE", "Incorporação", None, 15, [("passagem", "TI", 0)]),
        ("mobuss", "Criar obra no Mobuss", "Projetos", "Caique", 2, [("spe", "TI", 0)]),
        ("caixa", "Abrir a obra no apoio à produção Caixa", "Incorporação", "Luca", 10, [("spe", "TI", 0)]),
        ("fre", "FRE", "Projetos", "Eduardo", 5, [("passagem", "TI", 0)]),
        ("bep", "BEP (plano de execução BIM)", "Projetos", "Caique", 5, [("passagem", "TI", 0)]),
    ]),
    ("Levantamentos, laudos e estudos", [
        ("topo", "Levantamento topográfico planialtimétrico", "Projetos", None, 10, [("passagem", "TI", 0)]),
        ("sondagem", "Sondagem do terreno", "Projetos", None, 15, [("passagem", "TI", 0)]),
        ("ensaios", "Ensaios de solo", "Projetos", None, 10, [("sondagem", "TI", 0)]),
        ("ruido", "Ensaio de classe de ruído (análise de entorno)", "Projetos", None, 10, [("passagem", "TI", 0)]),
        ("ambiental", "Laudo de avaliação ambiental", "Projetos", None, 20, [("passagem", "TI", 0)]),
        ("vizinhanca", "Laudo de vizinhança", "Projetos", None, 10, [("passagem", "TI", 0)]),
        ("viabilidades", "Viabilidades Copel e Sanepar", "Incorporação", None, 30, [("passagem", "TI", 0)]),
    ]),
    ("Concepção do produto", [
        ("ep_impl", "Estudo preliminar de implantação", "Incorporação/Projetos", None, 15, [("topo", "TI", 0)]),
        ("ap_hab", "Ante-projeto de habitação com planta adaptada", "Incorporação", None, 15, [("ep_impl", "TI", 0)]),
        ("ap_impl", "Ante-projeto de implantação", "Incorporação", None, 15, [("ep_impl", "TI", 0)]),
        ("layout", "Definição final do layout das plantas", "Incorporação/Projetos", None, 10, [("ap_hab", "TI", 0)]),
        ("orc_prel", "Orçamento preliminar", "PCP", None, 10, [("ap_hab", "TI", 0)]),
        ("desempenho", "Simulação de desempenho (termo-lumínica e acústica)", "Projetos", None, 15,
         [("ruido", "TI", 0), ("ep_impl", "TI", 0)]),
    ]),
    ("Legalização do terreno", [
        ("terraplenagem", "Projeto de terraplenagem", "Projetos", None, 15,
         [("topo", "TI", 0), ("sondagem", "TI", 0), ("ambiental", "TI", 0), ("ep_impl", "TI", 0)]),
        ("rota", "Projeto de rota acessível", "Projetos", None, 10, [("terraplenagem", "TI", 0)]),
        ("contencoes", "Projeto de contenções", "Projetos", None, 20, [("terraplenagem", "TI", 0), ("sondagem", "TI", 0)]),
        ("ri", "Obtenção do RI", "Incorporação", None, 30, [("passagem", "TI", 0)]),
        ("transferencia", "Transferência do terreno", "Incorporação", None, 20, [("ri", "TI", 0)]),
        ("pgrcc", "Contratar PGRCC", "Incorporação", None, 10, [("ap_impl", "TI", 0)]),
    ]),
    ("Projetos legais e concessionárias", [
        ("copel", "Projeto Copel", "Projetos", None, 20, [("ap_impl", "TI", 0)]),
        ("sanepar", "Projeto Sanepar", "Projetos", None, 20, [("terraplenagem", "TI", 0)]),
        ("drenagem", "Projeto de drenagem", "Projetos", None, 15, [("terraplenagem", "TI", 0)]),
        ("aprov_drenagem", "Aprovação do projeto de drenagem", "Projetos", None, 20, [("drenagem", "TI", 0)]),
        ("paisagismo", "Projeto de paisagismo", "Incorporação", None, 15, [("ap_impl", "TI", 0)]),
        ("ap_incendio", "Ante-projeto de incêndio", "Projetos", None, 10, [("ep_impl", "TI", 0)]),
        ("memorial", "Memorial descritivo de habitação", "Projetos", "Ewander", 10, [("ap_impl", "TI", 0)]),
        ("aprov_conc", "Aprovação nas concessionárias (elétrico, hidráulico)", "Projetos", None, 30,
         [("paisagismo", "TI", 0), ("copel", "TI", 0), ("sanepar", "TI", 0)]),
        ("infra_ni", "Projetos de infraestrutura não incidentes", "Projetos", None, 20,
         [("paisagismo", "TI", 0), ("copel", "TI", 0), ("sanepar", "TI", 0)]),
    ]),
    ("Projetos executivos", [
        ("arq", "Projeto arquitetônico", "Projetos", "Ewander", 30, [("ap_impl", "TI", 0), ("layout", "TI", 0)]),
        ("estrutural", "Projeto estrutural", "Projetos", None, 40, [("arq", "II", 10), ("sondagem", "TI", 0)]),
        ("fundacoes", "Projeto de fundações", "Projetos", None, 25, [("estrutural", "II", 15), ("ensaios", "TI", 0)]),
        ("hidro", "Projeto hidrossanitário", "Projetos", None, 30, [("arq", "II", 10), ("sanepar", "TI", 0)]),
        ("eletrico", "Projeto elétrico", "Projetos", None, 30, [("arq", "II", 10), ("copel", "TI", 0)]),
        ("spda", "Projeto SPDA", "Projetos", None, 10, [("eletrico", "II", 0), ("estrutural", "II", 10)]),
        ("incendio", "Projeto de incêndio (PPCI)", "Projetos", None, 20, [("ap_incendio", "TI", 0), ("arq", "II", 10)]),
        ("gas", "Projeto de rede de gás", "Projetos", None, 15, [("ap_incendio", "II", 0)]),
        ("esquadrias", "Projeto de esquadrias", "Projetos", None, 15, [("arq", "TI", 0)]),
        ("pde", "PDE", "Projetos", None, 10, [("arq", "TI", 0)]),
        ("pct", "PCT", "Projetos", None, 10, [("arq", "TI", 0)]),
        ("selo_azul", "Obtenção do Selo Azul", "Projetos", None, 40, [("orc_prel", "TI", 0), ("gas", "TI", 0)]),
        ("compat", "Compatibilização", "Projetos", None, 20,
         [("estrutural", "TI", 0), ("fundacoes", "TI", 0), ("hidro", "TI", 0), ("eletrico", "TI", 0),
          ("spda", "TI", 0), ("incendio", "TI", 0), ("gas", "TI", 0), ("esquadrias", "TI", 0)]),
    ]),
    ("Análise de engenharia CEF (PJ)", [
        ("passagem_com", "Reunião de passagem para o comercial", "Incorporação/Projetos", None, 0,
         [("memorial", "TI", 0), ("layout", "TI", 0)]),
        ("cef1", "1ª análise de engenharia", "Projetos", None, 20,
         [("topo", "TI", 0), ("ambiental", "TI", 0), ("caixa", "TI", 0), ("viabilidades", "TI", 0),
          ("ap_hab", "TI", 0), ("ep_impl", "TI", 0), ("ri", "TI", 0), ("transferencia", "TI", 0)]),
        ("cef2", "2ª análise de engenharia", "Projetos", None, 15,
         [("cef1", "TI", 0), ("terraplenagem", "TI", 0), ("rota", "TI", 0), ("pgrcc", "TI", 0),
          ("layout", "TI", 0), ("gas", "TI", 0)]),
        ("cef3", "3ª análise de engenharia", "Projetos", None, 15,
         [("cef2", "TI", 0), ("paisagismo", "TI", 0), ("copel", "TI", 0), ("sanepar", "TI", 0),
          ("infra_ni", "TI", 0), ("passagem_com", "TI", 0)]),
        ("cef4", "4ª análise de engenharia", "Projetos", None, 15, [("cef3", "TI", 0)]),
        ("cef5", "5ª análise de engenharia", "Projetos", None, 15, [("cef4", "TI", 0)]),
    ]),
    ("PCP", [
        ("cronograma_obra", "Cronograma de obra", "PCP", None, 10, [("compat", "TI", 0)]),
        ("orcamento", "Orçamento executivo", "PCP", None, 20, [("compat", "TI", 0)]),
        ("4d", "Planejamento 4D", "PCP", None, 15, [("cronograma_obra", "TI", 0)]),
    ]),
]
