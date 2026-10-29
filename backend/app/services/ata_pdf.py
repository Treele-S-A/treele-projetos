"""A ata de análise crítica em PDF, no modelo da Treèle ENG-FL-001 (TREELE,
29/10/2026): o mesmo arquivo para todos, sem depender da impressão do
navegador. Ver docs/ata-analise-critica.md.

Cada página repete o cabeçalho (logo, título com a disciplina, ENG-FL-001 e
data) e a faixa do rodapé, como no Word. O corpo são faixas e tabelas
empilhadas, sem tabela dentro de tabela: assim a lista de itens quebra de
página normalmente.
"""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Table, TableStyle

PETROLEO = colors.HexColor("#00465c")
TRACO = colors.HexColor("#c9d1d4")
CINZA = colors.HexColor("#f2f4f5")
TEXTO = colors.HexColor("#1d2b30")
VERMELHO = colors.HexColor("#9c2f22")
LOGO = Path(__file__).parent / "logo-treele-construtora.png"

MARGEM = 16 * mm
LARGURA = A4[0] - 2 * MARGEM

_base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=12.2, textColor=TEXTO)
_faixa = ParagraphStyle("faixa", parent=_base, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)
_cab = ParagraphStyle("cab", parent=_base, fontSize=8.2, leading=10, textColor=PETROLEO, alignment=TA_CENTER)
_cab_tabela = ParagraphStyle("cab_tabela", parent=_cab, fontSize=7.4, leading=9)
_grupo = ParagraphStyle("grupo", parent=_base, fontName="Helvetica-Bold", textColor=PETROLEO)
_pequeno = ParagraphStyle("pequeno", parent=_base, fontSize=8.5, leading=11, textColor=colors.HexColor("#4a5a60"))
_centro = ParagraphStyle("centro", parent=_base, alignment=TA_CENTER)
_celula = ParagraphStyle("celula", parent=_centro, fontSize=8.6, leading=11)


def _p(texto: str, estilo=_base) -> Paragraph:
    return Paragraph(escape(texto).replace("\n", "<br/>"), estilo)


def _data(valor) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "-"


class Caixa(Flowable):
    """☐ / ☒ desenhados (a Helvetica não tem os caracteres)."""

    def __init__(self, marcada: bool, lado: float = 3.1 * mm):
        super().__init__()
        self.marcada = marcada
        self.lado = lado
        self.width = self.height = lado

    def draw(self):
        c, s = self.canv, self.lado
        c.setStrokeColor(TEXTO)
        c.setLineWidth(0.6)
        c.rect(0, 0, s, s)
        if self.marcada:
            c.line(0.6, 0.6, s - 0.6, s - 0.6)
            c.line(0.6, s - 0.6, s - 0.6, 0.6)


def _faixa_tabela(texto: str, espacada: bool = False, esquerda: bool = False) -> Table:
    if espacada:
        texto = "&nbsp;&nbsp;".join(" ".join(p) for p in texto.upper().split())
    estilo = ParagraphStyle("f", parent=_faixa, alignment=0 if esquerda else TA_CENTER)
    t = Table([[Paragraph(texto if espacada else escape(texto.upper()), estilo)]], colWidths=[LARGURA])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PETROLEO),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]))
    return t


def _caixa_texto(conteudo: list, padding_baixo: float = 6) -> Table:
    t = Table([[conteudo]], colWidths=[LARGURA])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, TRACO),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding_baixo),
    ]))
    return t


def gerar(dados: dict) -> bytes:
    """`dados`: o que a rota /atas/{id} devolve (AtaOut como dict)."""
    adjetivo = dados["adjetivo"]
    titulo = f"ANÁLISE CRÍTICA DE PROJETO {adjetivo.upper()}"
    data_ata = _data(dados["criada_em"])

    def pagina(canvas, doc):
        canvas.saveState()
        topo = A4[1] - 12 * mm
        canvas.drawImage(str(LOGO), MARGEM, topo - 13 * mm, width=33 * mm, height=15.5 * mm,
                         preserveAspectRatio=True, mask="auto")
        canvas.setFillColor(PETROLEO)
        canvas.setFont("Helvetica-Bold", 12.5)
        canvas.drawCentredString(A4[0] / 2 + 6 * mm, topo - 11 * mm, titulo)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.drawRightString(A4[0] - MARGEM, topo - 1 * mm, "ENG-FL-001")
        canvas.drawRightString(A4[0] - MARGEM, topo - 4.8 * mm, "DATA:")
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(A4[0] - MARGEM, topo - 8.6 * mm, data_ata)
        # Rodapé: número da página e a faixa.
        canvas.setFillColor(TEXTO)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawRightString(A4[0] - MARGEM - 4 * mm, 13 * mm, str(doc.page))
        canvas.setFillColor(PETROLEO)
        canvas.rect(0, 0, A4[0], 7 * mm, stroke=0, fill=1)
        canvas.restoreState()

    historia: list = []

    # Projeto
    historia.append(_faixa_tabela(f"Projeto {adjetivo}"))
    endereco = dados.get("obra_endereco")
    frase = (
        f"<b>Projeto {escape(adjetivo)}</b> do empreendimento {escape(dados['obra_nome'])}"
        + (f", localizado na {escape(endereco)}." if endereco else " (endereço não cadastrado).")
    )
    docs = "; ".join(
        f"{r['documento']} R{r['revisao']}" + (f" – {r['titulo']}" if r.get("titulo") else "")
        for r in dados["revisoes"]
    )
    rotulo_docs = "Documento analisado" if len(dados["revisoes"]) == 1 else "Documentos analisados"
    historia.append(_caixa_texto([Paragraph(frase, _base), _p(f"{rotulo_docs}: {docs}.", _pequeno)], 16))

    # Itens analisados
    historia.append(_faixa_tabela("Itens analisados", espacada=True))
    linhas = [[_p("SIM", _cab), _p("NÃO", _cab), _p("N/A", _cab), ""]]
    estilo_itens = [
        ("BOX", (0, 0), (-1, -1), 0.6, TRACO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (2, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]
    grupo_atual = None
    for item in dados["itens"]:
        if item.get("grupo") != grupo_atual:
            grupo_atual = item.get("grupo")
            linhas.append([_p(grupo_atual or "", _grupo), "", "", ""])
            n = len(linhas) - 1
            estilo_itens += [("SPAN", (0, n), (-1, n)), ("TOPPADDING", (0, n), (-1, n), 6)]
        texto = escape(f"{item['item']} {item['texto']}").replace("\n", "<br/>")
        if item.get("comentario"):
            texto += f'<br/><font color="#9c2f22"><i>Comentário: {escape(item["comentario"])}</i></font>'
        r = item.get("resposta")
        linhas.append([Caixa(r == "S"), Caixa(r == "N"), Caixa(r == "NA"), Paragraph(texto, _base)])
    if dados.get("observacoes"):
        linhas.append([Paragraph(f"<b>Observações:</b> {escape(dados['observacoes'])}".replace("\n", "<br/>"), _base), "", "", ""])
        n = len(linhas) - 1
        estilo_itens += [("SPAN", (0, n), (-1, n)), ("TOPPADDING", (0, n), (-1, n), 8)]
    col = 12 * mm
    tabela = Table(linhas, colWidths=[col, col, col, LARGURA - 3 * col], repeatRows=1)
    tabela.setStyle(TableStyle(estilo_itens))
    historia.append(tabela)

    # Solicitação de alterações: só a reprovação da revisão. Fica junto com
    # "Analisado por", numa página só.
    varias = len(dados["situacao"]) > 1
    cab = ["REVISÃO", "DATA DA\nSOLICITAÇÃO", "SOLICITANTE", "ALTERAÇÃO SOLICITADA", "DATA DO\nRECEBIMENTO"]
    linhas = [[_p(c, _cab_tabela) for c in cab]]
    for s in dados["situacao"]:
        if not s.get("motivo"):
            continue
        rev = (f"{s['documento']}\n" if varias else "") + f"R{s['revisao']}"
        linhas.append([
            _p(rev, _celula), _p(_data(s.get("reprovada_em")), _celula), _p(s.get("reprovada_por") or "-", _celula),
            _p(s["motivo"]), _p(_data(s.get("recebida_em")), _celula),
        ])
    while len(linhas) < 5:
        linhas.append(["", "", "", "", ""])
    larguras = [0.09, 0.12, 0.16, 0.50, 0.13]
    sol = Table(linhas, colWidths=[LARGURA * f for f in larguras], repeatRows=1, rowHeights=None)
    sol.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, TRACO),
        ("BACKGROUND", (0, 0), (-1, 0), CINZA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        *[("TOPPADDING", (0, i), (-1, i), 9) for i in range(1, len(linhas)) if linhas[i][0] == ""],
        *[("BOTTOMPADDING", (0, i), (-1, i), 9) for i in range(1, len(linhas)) if linhas[i][0] == ""],
    ]))
    historia.append(KeepTogether([
        _faixa_tabela("Solicitação de alterações", espacada=True),
        sol,
        _faixa_tabela("Analisado por:", esquerda=True),
        _caixa_texto([_p(dados["analisado_por"])], 7),
    ]))

    saida = BytesIO()
    doc = SimpleDocTemplate(
        saida, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM, topMargin=34 * mm, bottomMargin=20 * mm,
        title=f"{dados['codigo']} – {titulo.title()}", author="Treèle Construtora",
        subject=f"{dados['obra']} · {dados['disciplina']} · ENG-FL-001",
    )
    doc.build(historia, onFirstPage=pagina, onLaterPages=pagina)
    return saida.getvalue()
