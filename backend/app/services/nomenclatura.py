"""Validação e leitura do nome de arquivo.

O padrão é escrito num template legível, não em regex crua, para que um
coordenador consiga ajustá-lo sem programador:

    {obra}-{disciplina}-{fase}-{prancha}-R{revisao}

Cada token tem um tipo, e o tipo define tanto o formato aceito quanto a
validação semântica: um token `disciplina` só passa se o código existir no
cadastro de disciplinas. É isso que diferencia "o nome tem o formato certo" de
"o nome está certo".

Além de barrar o upload, o parser **extrai** os campos — obra, disciplina,
fase, revisão. Ninguém digita metadado à mão, e por isso ninguém erra o
cadastro.
"""

import re
import unicodedata
from dataclasses import dataclass, field

# Tokens que compõem a identidade do documento. A revisão fica de fora (é o que
# muda) e o texto descritivo também (o título pode ser corrigido entre revisões
# sem que vire outro documento).
TIPOS_IDENTIDADE = ("obra", "disciplina", "fase", "numero", "codigo")

TIPOS_VALIDOS = (
    "obra",
    "disciplina",
    "fase",
    "numero",
    "codigo",
    "revisao",
    "texto",
    "livre",
)

_RE_TOKEN = re.compile(r"\{(\w+)\}")


@dataclass
class ResultadoNome:
    valido: bool
    erros: list[str] = field(default_factory=list)
    campos: dict[str, str] = field(default_factory=dict)

    codigo_documento: str | None = None
    obra_codigo: str | None = None
    disciplina_codigo: str | None = None
    fase_codigo: str | None = None
    revisao_numero: str | None = None
    revisao_ordem: int = 0
    titulo: str | None = None
    extensao: str | None = None


# --------------------------------------------------------------------------
# Compilação do template
# --------------------------------------------------------------------------


def partes_template(template: str) -> list[tuple[str, str]]:
    """Quebra o template em ("literal", texto) e ("token", nome)."""
    partes: list[tuple[str, str]] = []
    pos = 0
    for m in _RE_TOKEN.finditer(template):
        if m.start() > pos:
            partes.append(("literal", template[pos : m.start()]))
        partes.append(("token", m.group(1)))
        pos = m.end()
    if pos < len(template):
        partes.append(("literal", template[pos:]))
    return partes


def _regex_de_token(spec: dict) -> str:
    tipo = spec.get("tipo", "texto")
    if tipo in ("obra", "disciplina", "fase"):
        return r"[A-Za-z0-9]+"
    if tipo == "numero":
        digitos = spec.get("digitos")
        return rf"\d{{{int(digitos)}}}" if digitos else r"\d+"
    if tipo == "revisao":
        if spec.get("formato", "numerico") == "alfabetico":
            return r"[A-Za-z]{1,2}"
        digitos = spec.get("digitos")
        return rf"\d{{{int(digitos)}}}" if digitos else r"\d+"
    if tipo == "codigo":
        # Formato livre — o número da prancha varia por escritório e por obra
        # ("001", "PAV1", "01.A", "T-04"). Aceita hífen: como obra, disciplina
        # e fase não têm hífen e a revisão fica ancorada no fim do nome, o
        # retrocesso da regex ainda separa os campos sem ambiguidade.
        return r"[A-Za-z0-9À-ÿ._-]+"
    if tipo == "texto":
        # Sem hífen nem underscore: assim os separadores do template continuam
        # delimitando o campo em vez de serem engolidos por ele.
        return r"[A-Za-z0-9À-ÿ. ]+"
    return r"[^\\/]+"


def compilar(template: str, tokens: dict) -> tuple[re.Pattern, re.Pattern]:
    """Devolve (regex estrita, regex frouxa).

    A frouxa aceita qualquer conteúdo em cada token e serve só para
    diagnosticar *qual* campo está errado quando a estrita falha.
    """
    estrita, frouxa = [], []
    for kind, valor in partes_template(template):
        if kind == "literal":
            escapado = re.escape(valor)
            estrita.append(escapado)
            frouxa.append(escapado)
        else:
            spec = tokens.get(valor, {"tipo": "texto"})
            estrita.append(f"(?P<{valor}>{_regex_de_token(spec)})")
            frouxa.append(f"(?P<{valor}>.+?)")
    return (
        re.compile("^" + "".join(estrita) + "$", re.IGNORECASE),
        re.compile("^" + "".join(frouxa) + "$", re.IGNORECASE),
    )


def validar_definicao(template: str, tokens: dict) -> list[str]:
    """Confere se o próprio padrão faz sentido, antes de salvá-lo."""
    erros: list[str] = []
    nomes = [v for k, v in partes_template(template) if k == "token"]

    if not nomes:
        erros.append("O template precisa ter ao menos um campo entre chaves, ex.: {obra}.")

    for nome in nomes:
        spec = tokens.get(nome)
        if spec is None:
            erros.append(f"O campo {{{nome}}} aparece no template mas não foi definido.")
            continue
        tipo = spec.get("tipo")
        if tipo not in TIPOS_VALIDOS:
            erros.append(
                f"O campo {{{nome}}} tem tipo '{tipo}' desconhecido. "
                f"Use um destes: {', '.join(TIPOS_VALIDOS)}."
            )

    sobrando = set(tokens) - set(nomes)
    if sobrando:
        erros.append(
            "Estes campos foram definidos mas não aparecem no template: "
            + ", ".join(sorted(sobrando))
        )

    revisoes = [n for n in nomes if tokens.get(n, {}).get("tipo") == "revisao"]
    if len(revisoes) != 1:
        erros.append(
            "O template precisa ter exatamente um campo do tipo 'revisao' "
            f"(encontrei {len(revisoes)})."
        )

    identidade = [
        n for n in nomes if tokens.get(n, {}).get("tipo") in TIPOS_IDENTIDADE
    ]
    if not identidade:
        erros.append(
            "O template precisa ter ao menos um campo de identidade "
            f"({', '.join(TIPOS_IDENTIDADE)}) para formar o código do documento."
        )

    # Disciplina e fase são obrigatórias: é por elas que o acervo é filtrado, e
    # extraí-las do nome é o que dispensa cadastro manual a cada envio.
    for exigido in ("disciplina", "fase"):
        if not any(tokens.get(n, {}).get("tipo") == exigido for n in nomes):
            erros.append(
                f"O template precisa ter um campo do tipo '{exigido}'. "
                "Sem ele o sistema não consegue classificar o arquivo sozinho."
            )

    return erros


# --------------------------------------------------------------------------
# Revisões
# --------------------------------------------------------------------------


def ordem_revisao(valor: str, formato: str = "numerico") -> int:
    """'02' → 2 e 'B' → 2, para ordenar e achar a revisão anterior."""
    if formato == "alfabetico":
        total = 0
        for ch in valor.upper():
            if not ("A" <= ch <= "Z"):
                return 0
            total = total * 26 + (ord(ch) - 64)
        return total
    try:
        return int(valor)
    except ValueError:
        return 0


def normalizar_revisao(valor: str, spec: dict) -> str:
    if spec.get("formato", "numerico") == "alfabetico":
        return valor.upper()
    digitos = spec.get("digitos")
    return valor.zfill(int(digitos)) if digitos else valor.lstrip("0") or "0"


# --------------------------------------------------------------------------
# Análise de um nome de arquivo
# --------------------------------------------------------------------------


def _rotulo(nome: str, spec: dict) -> str:
    return spec.get("rotulo") or nome


def _descrever_esperado(nome: str, spec: dict) -> str:
    tipo = spec.get("tipo", "texto")
    if tipo == "obra":
        return "o código da obra"
    if tipo == "disciplina":
        return "um código de disciplina cadastrado (ex.: ARQ, EST, HID)"
    if tipo == "fase":
        return "um código de fase cadastrado (ex.: EP, AP, PE)"
    if tipo == "numero":
        d = spec.get("digitos")
        return f"{d} dígitos" if d else "apenas dígitos"
    if tipo == "codigo":
        return "letras, números, ponto, hífen ou underscore (sem barras)"
    if tipo == "revisao":
        if spec.get("formato", "numerico") == "alfabetico":
            return "uma ou duas letras (A, B, … AA)"
        d = spec.get("digitos")
        return f"{d} dígitos" if d else "apenas dígitos"
    if tipo == "texto":
        return "letras, números, ponto e espaço (sem hífen nem underscore)"
    return "um valor"


def analisar(
    nome_arquivo: str,
    template: str,
    tokens: dict,
    extensoes: list[str],
    *,
    obra_codigo: str | None = None,
    disciplinas: set[str] | None = None,
    fases: set[str] | None = None,
) -> ResultadoNome:
    """Valida o nome e extrai os metadados.

    `disciplinas` e `fases` são os códigos cadastrados, em maiúsculas.
    `obra_codigo` é a obra de destino do upload — se informado, o campo de obra
    do nome precisa bater com ela (evita subir arquivo na obra errada).
    """
    disciplinas = {d.upper() for d in (disciplinas or set())}
    fases = {f.upper() for f in (fases or set())}

    res = ResultadoNome(valido=False)
    nome = nome_arquivo.strip()

    if "." not in nome:
        res.erros.append("O arquivo precisa ter extensão (ex.: .pdf, .dwg, .ifc).")
        return res

    base, _, ext = nome.rpartition(".")
    ext = ext.lower()
    res.extensao = ext

    permitidas = [e.lower() for e in extensoes]
    if ext not in permitidas:
        res.erros.append(
            f"Extensão .{ext} não é aceita. Aceitas: "
            + ", ".join(f".{e}" for e in permitidas)
            + "."
        )
        return res

    estrita, frouxa = compilar(template, tokens)
    m = estrita.fullmatch(base)

    if not m:
        m_frouxa = frouxa.fullmatch(base)
        if not m_frouxa:
            res.erros.append(
                f"O nome não segue o padrão da obra. Esperado: {template} "
                f"(confira os separadores e a quantidade de campos)."
            )
            return res
        # A estrutura bate; algum campo tem conteúdo inválido. Aponta qual.
        for nome_tok, valor in m_frouxa.groupdict().items():
            spec = tokens.get(nome_tok, {"tipo": "texto"})
            if not re.fullmatch(_regex_de_token(spec), valor or "", re.IGNORECASE):
                res.erros.append(
                    f"O campo '{_rotulo(nome_tok, spec)}' está como '{valor}', "
                    f"mas deveria ter {_descrever_esperado(nome_tok, spec)}."
                )
        if not res.erros:
            res.erros.append(f"O nome não segue o padrão da obra. Esperado: {template}")
        return res

    campos = {k: (v or "") for k, v in m.groupdict().items()}

    # --- validação semântica, na ordem em que aparecem no template ----------
    identidade: list[str] = []
    for kind, nome_tok in partes_template(template):
        if kind != "token":
            continue
        spec = tokens.get(nome_tok, {"tipo": "texto"})
        tipo = spec.get("tipo", "texto")
        valor = campos.get(nome_tok, "")

        if tipo in TIPOS_IDENTIDADE:
            valor = valor.upper()
            campos[nome_tok] = valor
            identidade.append(valor)

        if tipo == "obra":
            res.obra_codigo = valor
            if obra_codigo and valor != obra_codigo.upper():
                res.erros.append(
                    f"O nome diz que este arquivo é da obra '{valor}', "
                    f"mas o envio é para a obra '{obra_codigo.upper()}'."
                )
        elif tipo == "disciplina":
            res.disciplina_codigo = valor
            if disciplinas and valor not in disciplinas:
                res.erros.append(
                    f"Disciplina '{valor}' não está cadastrada. "
                    f"Disciplinas válidas: {', '.join(sorted(disciplinas))}."
                )
        elif tipo == "fase":
            res.fase_codigo = valor
            if fases and valor not in fases:
                res.erros.append(
                    f"Fase '{valor}' não está cadastrada. "
                    f"Fases válidas: {', '.join(sorted(fases))}."
                )
        elif tipo == "revisao":
            res.revisao_numero = normalizar_revisao(valor, spec)
            res.revisao_ordem = ordem_revisao(valor, spec.get("formato", "numerico"))
            campos[nome_tok] = res.revisao_numero
        elif tipo == "texto":
            res.titulo = valor.strip()

    res.campos = campos
    res.codigo_documento = "-".join(identidade)
    res.valido = not res.erros
    return res


def texto_sem_acento(valor: str) -> str:
    """Usado na busca, para 'hidráulico' encontrar 'hidraulico'."""
    nfkd = unicodedata.normalize("NFKD", valor)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# Padrão global usado por obras que não definiram o seu.
PADRAO_INICIAL = {
    "nome": "Padrão Treèle",
    "template": "{obra}-{disciplina}-{fase}-{prancha}-R{revisao}",
    "tokens": {
        "obra": {"tipo": "obra", "rotulo": "obra"},
        "disciplina": {"tipo": "disciplina", "rotulo": "disciplina"},
        "fase": {"tipo": "fase", "rotulo": "fase"},
        "prancha": {"tipo": "codigo", "rotulo": "número da prancha"},
        "revisao": {
            "tipo": "revisao",
            "formato": "numerico",
            "digitos": 2,
            "rotulo": "revisão",
        },
    },
    "extensoes": ["dwg", "rvt", "pdf", "ifc"],
    "exemplo": "TRL001-ARQ-PE-001-R00.pdf",
}
