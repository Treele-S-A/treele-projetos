"""Prepara o PDF de uma prancha para o assistente ler (16/10/2026).

O modelo recebe o PDF como imagem reduzida: numa A0, a letra das anotações
vira poucos pixels e some ("Caixa d'água de polietileno, 1000 litros" não foi
lida no MIL-HID-PE-AF). Por isso a leitura leva, junto do PDF:

- o TEXTO da prancha, extraído aqui — exato, mas sem a posição no desenho;
- RECORTES ampliados das páginas grandes que não têm texto (o CAD exportou as
  letras como desenho, comum nas pranchas de estrutura): a página é dividida
  numa grade, e cada pedaço vai como imagem em resolução de leitura.

Numa amostra de 40 PDFs do acervo, 32 tinham o texto todo como texto e 8
quase nada (só o carimbo, ou nem isso).

Motor: pypdfium2 (o PDFium do Chrome, licença livre para uso comercial).
"""

import io
import logging
from dataclasses import dataclass, field

import pypdfium2 as pdfium

log = logging.getLogger("treele.chat")

# O texto vai inteiro para o modelo; prancha comum tem de 1 a 10 mil.
MAX_TEXTO = 30_000
# Página com menos texto que isto teve as letras exportadas como desenho.
TEXTO_MINIMO_POR_PAGINA = 400
# Só vale ampliar o que é maior que uma A3 (em pontos: 1 pt = 1/72 pol).
AREA_A3 = 1191 * 842
# Lado maior da página renderizada: numa A0 dá uns 5 px por mm, letra de
# 2,5 mm com 12 px de altura. Grade de 4 x 3 (ou 3 x 4 em retrato).
LADO_MAIOR_PX = 6000
GRADE = (4, 3)
SOBREPOSICAO = 0.06  # texto cortado na divisa aparece inteiro no vizinho
MAX_PAGINAS_AMPLIADAS = 2
QUALIDADE_JPEG = 82


@dataclass
class Recorte:
    pagina: int
    linha: int
    coluna: int
    jpeg: bytes


@dataclass
class Preparado:
    texto: str = ""
    paginas: int = 0
    recortes: list[Recorte] = field(default_factory=list)

    def descricao_recortes(self) -> str:
        if not self.recortes:
            return ""
        paginas = sorted({r.pagina for r in self.recortes})
        return (
            f"Seguem também {len(self.recortes)} recortes AMPLIADOS da(s) página(s) "
            f"{', '.join(map(str, paginas))}, que não têm texto selecionável (as letras "
            "são desenho). Cada recorte diz página, linha e coluna da grade, contadas "
            "de cima para baixo e da esquerda para a direita; recortes vizinhos se "
            "sobrepõem um pouco. Leia as anotações miúdas neles."
        )


def preparar(dados: bytes) -> Preparado:
    """Nunca derruba a leitura: PDF que o PDFium não abre vai só como PDF."""
    try:
        documento = pdfium.PdfDocument(dados)
    except Exception as erro:  # noqa: BLE001 — PDF estranho não pode parar o chat
        log.warning("Leitura: PDF não abriu no PDFium (%s).", type(erro).__name__)
        return Preparado()
    preparado = Preparado(paginas=len(documento))
    partes = []
    ampliar = []
    for indice in range(len(documento)):
        pagina = documento[indice]
        texto = pagina.get_textpage().get_text_bounded().replace("\r\n", "\n").strip()
        if texto:
            partes.append(f"--- Página {indice + 1} ---\n{texto}")
        largura, altura = pagina.get_size()
        if len(texto) < TEXTO_MINIMO_POR_PAGINA and largura * altura > AREA_A3:
            ampliar.append(indice)
    preparado.texto = "\n\n".join(partes)[:MAX_TEXTO]
    for indice in ampliar[:MAX_PAGINAS_AMPLIADAS]:
        try:
            preparado.recortes += _recortar(documento[indice], indice + 1)
        except Exception as erro:  # noqa: BLE001
            log.warning("Leitura: falha ao ampliar a página %s (%s).", indice + 1, erro)
    return preparado


def _recortar(pagina, numero: int) -> list[Recorte]:
    largura, altura = pagina.get_size()
    escala = LADO_MAIOR_PX / max(largura, altura)
    imagem = pagina.render(scale=escala).to_pil().convert("RGB")
    colunas, linhas = GRADE if largura >= altura else GRADE[::-1]
    passo_x, passo_y = imagem.width / colunas, imagem.height / linhas
    folga_x, folga_y = passo_x * SOBREPOSICAO, passo_y * SOBREPOSICAO
    recortes = []
    for linha in range(linhas):
        for coluna in range(colunas):
            caixa = (
                max(0, int(coluna * passo_x - folga_x)),
                max(0, int(linha * passo_y - folga_y)),
                min(imagem.width, int((coluna + 1) * passo_x + folga_x)),
                min(imagem.height, int((linha + 1) * passo_y + folga_y)),
            )
            pedaco = imagem.crop(caixa)
            # Pedaço todo em branco não diz nada e custa como os outros.
            if pedaco.convert("L").getextrema()[0] > 245:
                continue
            saida = io.BytesIO()
            pedaco.save(saida, format="JPEG", quality=QUALIDADE_JPEG)
            recortes.append(Recorte(numero, linha + 1, coluna + 1, saida.getvalue()))
    return recortes
