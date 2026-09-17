"""Testes do parser de nomenclatura — a regra que barra o acervo bagunçado."""

from app.services.nomenclatura import (
    PADRAO_INICIAL,
    analisar,
    ordem_revisao,
    validar_definicao,
)

DISCIPLINAS = {"ARQ", "EST", "HID"}
FASES = {"EP", "PE"}


def _analisar(nome, obra="TRL001"):
    return analisar(
        nome,
        PADRAO_INICIAL["template"],
        PADRAO_INICIAL["tokens"],
        PADRAO_INICIAL["extensoes"],
        obra_codigo=obra,
        disciplinas=DISCIPLINAS,
        fases=FASES,
    )


def test_nome_valido_extrai_todos_os_campos():
    r = _analisar("TRL001-ARQ-PE-001-R00.pdf")
    assert r.valido, r.erros
    assert r.obra_codigo == "TRL001"
    assert r.disciplina_codigo == "ARQ"
    assert r.fase_codigo == "PE"
    assert r.revisao_numero == "00"
    assert r.revisao_ordem == 0
    assert r.codigo_documento == "TRL001-ARQ-PE-001"
    assert r.extensao == "pdf"


def test_revisao_maior_tem_ordem_maior():
    r0 = _analisar("TRL001-ARQ-PE-001-R00.pdf")
    r7 = _analisar("TRL001-ARQ-PE-001-R07.pdf")
    assert r7.revisao_ordem > r0.revisao_ordem
    # Mesmo documento, revisões diferentes.
    assert r0.codigo_documento == r7.codigo_documento


def test_disciplina_inexistente_e_recusada_com_lista_de_validas():
    r = _analisar("TRL001-XYZ-PE-001-R00.pdf")
    assert not r.valido
    assert any("XYZ" in e and "ARQ" in e for e in r.erros)


def test_fase_inexistente_e_recusada():
    r = _analisar("TRL001-ARQ-ZZ-001-R00.pdf")
    assert not r.valido
    assert any("Fase" in e for e in r.erros)


def test_obra_divergente_e_recusada():
    """Nome diz TRL999 mas o envio é para a TRL001 — erro clássico de pasta."""
    r = _analisar("TRL999-ARQ-PE-001-R00.pdf", obra="TRL001")
    assert not r.valido
    assert any("TRL999" in e for e in r.erros)


def test_numero_da_prancha_e_livre():
    """A TREELE numera prancha de formas diferentes por obra (17/09/2026)."""
    for prancha in ["001", "1", "PAV1", "01.A", "T-04", "AP_12", "CORTE.AA"]:
        r = _analisar(f"TRL001-ARQ-PE-{prancha}-R00.pdf")
        assert r.valido, (prancha, r.erros)
        assert r.codigo_documento == f"TRL001-ARQ-PE-{prancha.upper()}"


def test_prancha_com_hifen_nao_confunde_a_revisao():
    """O campo livre aceita hífen, mas a revisão fica ancorada no fim."""
    r = _analisar("TRL001-EST-PE-T-04-R07.dwg")
    assert r.valido, r.erros
    assert r.codigo_documento == "TRL001-EST-PE-T-04"
    assert r.revisao_numero == "07"


def test_prancha_com_barra_e_recusada():
    """Barra viraria subpasta no storage — o campo livre para aí."""
    r = _analisar("TRL001-ARQ-PE-01/02-R00.pdf")
    assert not r.valido


def test_revisao_fora_de_dois_digitos_aponta_o_campo():
    r = _analisar("TRL001-ARQ-PE-001-R1.pdf")
    assert not r.valido
    assert any("revis" in e for e in r.erros), r.erros


def test_estrutura_totalmente_fora_do_padrao():
    r = _analisar("planta forma pav tipo REV FINAL (2).pdf")
    assert not r.valido
    assert any("padrão" in e.lower() for e in r.erros)


def test_extensao_nao_aceita():
    r = _analisar("TRL001-ARQ-PE-001-R00.docx")
    assert not r.valido
    assert any(".docx" in e for e in r.erros)


def test_arquivo_sem_extensao():
    r = _analisar("TRL001-ARQ-PE-001-R00")
    assert not r.valido


def test_nome_aceita_caixa_baixa_e_normaliza():
    r = _analisar("trl001-arq-pe-001-r00.PDF")
    assert r.valido, r.erros
    assert r.disciplina_codigo == "ARQ"
    assert r.codigo_documento == "TRL001-ARQ-PE-001"


def test_ordem_revisao_alfabetica():
    assert ordem_revisao("A", "alfabetico") == 1
    assert ordem_revisao("B", "alfabetico") == 2
    assert ordem_revisao("AA", "alfabetico") == 27
    assert ordem_revisao("03") == 3


def test_definicao_exige_campo_de_revisao():
    erros = validar_definicao(
        "{obra}-{disciplina}-{fase}",
        {
            "obra": {"tipo": "obra"},
            "disciplina": {"tipo": "disciplina"},
            "fase": {"tipo": "fase"},
        },
    )
    assert any("revisao" in e for e in erros)


def test_definicao_exige_disciplina_e_fase():
    erros = validar_definicao(
        "{obra}-R{revisao}",
        {"obra": {"tipo": "obra"}, "revisao": {"tipo": "revisao"}},
    )
    assert any("disciplina" in e for e in erros)
    assert any("fase" in e for e in erros)


def test_definicao_valida_do_padrao_inicial():
    assert validar_definicao(PADRAO_INICIAL["template"], PADRAO_INICIAL["tokens"]) == []


def test_template_alternativo_com_underscore_e_titulo():
    template = "{obra}_{disciplina}_{fase}_{seq}_REV{revisao}_{titulo}"
    tokens = {
        "obra": {"tipo": "obra"},
        "disciplina": {"tipo": "disciplina"},
        "fase": {"tipo": "fase"},
        "seq": {"tipo": "numero", "digitos": 2},
        "revisao": {"tipo": "revisao", "formato": "alfabetico"},
        "titulo": {"tipo": "texto"},
    }
    assert validar_definicao(template, tokens) == []

    r = analisar(
        "TRL001_EST_PE_07_REVB_Forma Pav Tipo.dwg",
        template,
        tokens,
        ["dwg"],
        obra_codigo="TRL001",
        disciplinas=DISCIPLINAS,
        fases=FASES,
    )
    assert r.valido, r.erros
    assert r.revisao_numero == "B"
    assert r.revisao_ordem == 2
    assert r.titulo == "Forma Pav Tipo"
    assert r.codigo_documento == "TRL001-EST-PE-07"
