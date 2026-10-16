"""Leitura de prancha pelo chat (16/10/2026): o texto do PDF vai junto da
leitura, e a página grande sem texto vai também em recortes ampliados."""

import base64
import json

from app.config import settings
from app.services import chat_claude, chat_modelo, pdf_leitura

A0 = (3370, 2384)  # pontos (1/72 pol), paisagem
A4 = (595, 842)


def _pdf(largura, altura, conteudo: bytes, com_fonte=True) -> bytes:
    """PDF de uma página, montado à mão (o PDFium refaz a tabela xref)."""
    recursos = b"/Resources << /Font << /F1 4 0 R >> >>" if com_fonte else b""
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] %s /Contents 5 0 R >>"
        % (largura, altura, recursos),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(conteudo), conteudo),
    ]
    saida = b"%PDF-1.7\n"
    for i, corpo in enumerate(objetos, 1):
        saida += b"%d 0 obj\n%s\nendobj\n" % (i, corpo)
    return saida + b"trailer\n<< /Root 1 0 R /Size 6 >>\n%%EOF\n"


def _texto(frase: str) -> bytes:
    return b"BT /F1 12 Tf 100 100 Td (%s) Tj ET" % frase.encode("latin-1")


# Um traço grosso em cada canto: o resto da folha fica em branco.
DESENHO = b"20 w 0 0 m 200 200 l S 3370 2384 m 3170 2184 l S"


def test_texto_da_prancha_e_extraido():
    # Prancha de verdade tem centenas de caracteres; menos que isso conta como
    # letra exportada como desenho.
    notas = " ".join(f"Nota {n}: ver detalhe." for n in range(1, 30))
    p = pdf_leitura.preparar(_pdf(*A0, _texto(f"Caixa d'agua de polietileno, 1000 litros. {notas}")))
    assert p.paginas == 1
    assert "1000 litros" in p.texto and "Página 1" in p.texto
    assert p.recortes == []  # tem texto: não precisa ampliar


def test_pagina_grande_sem_texto_vira_recortes_e_branco_fica_de_fora():
    p = pdf_leitura.preparar(_pdf(*A0, DESENHO, com_fonte=False))
    assert p.texto == ""
    # Grade 4 x 3; só os dois cantos com traço têm desenho.
    assert {(r.linha, r.coluna) for r in p.recortes} == {(1, 4), (3, 1)}
    assert all(r.jpeg.startswith(b"\xff\xd8") for r in p.recortes)  # JPEG
    assert "2 recortes AMPLIADOS" in p.descricao_recortes()


def test_pagina_pequena_sem_texto_nao_e_ampliada():
    assert pdf_leitura.preparar(_pdf(*A4, b"20 w 0 0 m 200 200 l S", com_fonte=False)).recortes == []


def test_pdf_que_nao_abre_vai_so_como_pdf():
    p = pdf_leitura.preparar(b"isto nao e um pdf")
    assert (p.texto, p.recortes) == ("", [])
    assert chat_modelo.instrucao_leitura("X", "?", p) == chat_modelo.LEITURA.format(codigo="X", pergunta="?")


def test_claude_recebe_pdf_recortes_e_texto(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "chave-de-teste")
    monkeypatch.setattr(settings, "chat_fornecedor", "")
    preparado = pdf_leitura.Preparado(
        texto="--- Página 1 ---\nCaixa D'Água 1000L", paginas=1,
        recortes=[pdf_leitura.Recorte(1, 2, 3, b"\xff\xd8jpeg")],
    )
    monkeypatch.setattr(pdf_leitura, "preparar", lambda dados: preparado)
    corpos = []
    monkeypatch.setattr(chat_claude, "_chamar", lambda corpo, tempo=None: corpos.append(corpo)
                        or {"content": [{"type": "text", "text": "1000 litros."}]})

    assert chat_modelo.ler_pdf(b"%PDF", "Qual o volume?", "MIL-HID-PE-AF") == "1000 litros."
    documento, rotulo, imagem, pedido = corpos[0]["messages"][0]["content"]
    assert documento["type"] == "document"
    assert rotulo["text"] == "Recorte ampliado: página 1, linha 2, coluna 3."
    assert imagem["source"]["media_type"] == "image/jpeg"
    assert base64.b64decode(imagem["source"]["data"]) == b"\xff\xd8jpeg"
    assert "Qual o volume?" in pedido["text"]
    assert "<texto_da_prancha>\n--- Página 1 ---\nCaixa D'Água 1000L" in pedido["text"]
    assert "1 recortes AMPLIADOS" in pedido["text"]
    assert corpos[0]["max_tokens"] == chat_claude.MAX_TOKENS_LEITURA


def test_gemini_recebe_pdf_recortes_e_texto(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "chave-de-teste")
    pdf = _pdf(*A0, _texto("Caixa 1000L"))
    corpos = []

    def falso(corpo, tempo=None, modelo=None):
        corpos.append(json.loads(json.dumps(corpo)))
        return {"candidates": [{"content": {"parts": [{"text": "1000 L."}]}}]}

    monkeypatch.setattr(chat_modelo, "_chamar", falso)
    assert chat_modelo.ler_pdf(pdf, "Volume?", "X") == "1000 L."
    partes = corpos[0]["contents"][0]["parts"]
    assert partes[0]["inlineData"]["mimeType"] == "application/pdf"
    assert "Caixa 1000L" in partes[-1]["text"] and "Volume?" in partes[-1]["text"]
