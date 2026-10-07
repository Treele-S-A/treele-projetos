"""A conversa com o modelo de IA — hoje o Gemini, pela API nativa.

Tudo que é específico do fornecedor mora aqui: o formato da chamada, das
ferramentas e da resposta. Trocar de fornecedor (Claude, Gemini pago, outro)
é reescrever este arquivo; as ferramentas (chat_ferramentas.py) e a rota não
mudam.

API nativa, e não a "compatível com OpenAI": nesta, o Gemini 3 tem problemas
conhecidos justamente com várias rodadas de consulta, que é o uso aqui.

O ciclo: a IA lê a pergunta e pede consultas; o servidor roda cada uma com as
permissões de quem pergunta e devolve o resultado; a IA responde com base
nele. Cada parte que a IA devolve volta a ela intacta — inclusive a
"assinatura de pensamento" do Gemini 3, sem a qual ele se perde entre uma
rodada e outra.
"""

import base64
import logging
import time
from dataclasses import dataclass

import httpx

from ..config import settings
from .chat_ferramentas import DECLARACOES, Ferramentas

log = logging.getLogger("treele.chat")

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
# A função tem 60 s na Vercel; a soma das rodadas precisa caber nisso.
TEMPO_POR_CHAMADA = 20
# Ler um PDF de prancha leva mais.
TEMPO_LEITURA_PDF = 35
MAX_RODADAS = 6


class ChatIndisponivel(Exception):
    """Falha que a pessoa precisa ver explicada (limite, chave, rede).

    `detalhe` é o motivo técnico — o código e a mensagem do fornecedor, nunca
    a chave. A rota mostra só para administrador: é o que permite resolver
    sem abrir o log da hospedagem."""

    def __init__(self, mensagem: str, detalhe: str | None = None):
        super().__init__(mensagem)
        self.detalhe = detalhe


class Sobrecarga(ChatIndisponivel):
    """O modelo está sobrecarregado (500/503) — vale tentar de novo ou outro."""


class CotaEsgotada(Sobrecarga):
    """A cota gratuita deste modelo acabou (429). Repetir nele não adianta; a
    cota é por modelo, então o reserva ainda tem a dele."""


# Tentativas diante de sobrecarga: o principal, ele de novo após uma pausa, e o
# reserva. 503 volta rápido, então as três cabem no tempo da função.
PAUSA_ANTES_DE_REPETIR = 2.0


def _tentativas() -> list[tuple[str, float]]:
    principal, reserva = settings.chat_modelo, settings.chat_modelo_reserva
    tentativas = [(principal, 0.0), (principal, PAUSA_ANTES_DE_REPETIR)]
    if reserva and reserva != principal:
        tentativas.append((reserva, 0.0))
    return tentativas


def _com_reserva(fazer):
    """Roda `fazer(modelo)` nas tentativas, enquanto o Google disser que está
    sobrecarregado ou sem cota. Outro erro qualquer não se repete: seria o
    mesmo de novo. Cota esgotada pula direto para o próximo modelo."""
    ultimo: Sobrecarga | None = None
    sem_cota: set[str] = set()
    for modelo, pausa in _tentativas():
        if modelo in sem_cota:
            continue
        if pausa:
            time.sleep(pausa)
        try:
            return fazer(modelo)
        except CotaEsgotada as erro:
            log.warning("Chat: cota de %s esgotada (%s).", modelo, erro.detalhe)
            sem_cota.add(modelo)
            ultimo = erro
        except Sobrecarga as erro:
            log.warning("Chat: %s sobrecarregado (%s).", modelo, erro.detalhe)
            ultimo = erro
    raise ultimo


@dataclass
class Turno:
    papel: str  # "usuario" ou "assistente"
    texto: str


def _motivo(r: httpx.Response) -> str:
    """Código e mensagem do erro do Gemini. A resposta de erro não traz a
    chave (ela vai no cabeçalho, não no corpo)."""
    try:
        mensagem = r.json().get("error", {}).get("message", "")
    except ValueError:
        mensagem = r.text
    return f"{r.status_code} {mensagem}"[:400]


def _chamar(corpo: dict, tempo: float = TEMPO_POR_CHAMADA, modelo: str | None = None) -> dict:
    try:
        r = httpx.post(
            URL.format(modelo=modelo or settings.chat_modelo),
            headers={"x-goog-api-key": settings.gemini_api_key},
            json=corpo,
            timeout=tempo,
        )
    except httpx.HTTPError as erro:
        log.error("Chat: sem resposta do modelo (%s).", type(erro).__name__)
        raise ChatIndisponivel(
            "O assistente não respondeu a tempo. Tente de novo.", type(erro).__name__
        ) from erro
    if r.status_code == 429:
        raise CotaEsgotada(
            "O limite gratuito de perguntas foi atingido por agora. Espere um minuto e "
            "tente de novo.",
            _motivo(r),
        )
    if r.status_code in (401, 403):
        log.error("Chat: chave recusada (%s).", r.status_code)
        raise ChatIndisponivel(
            "O assistente está mal configurado (chave recusada).", _motivo(r)
        )
    if r.status_code in (500, 503):
        raise Sobrecarga(
            "O serviço de IA do Google está sobrecarregado agora. Tente de novo em "
            "alguns minutos.",
            _motivo(r),
        )
    if r.status_code >= 400:
        # Só o código e o começo da mensagem: o corpo da pergunta não vai ao log.
        log.error("Chat: erro %s do modelo: %s", r.status_code, r.text[:300])
        raise ChatIndisponivel(
            "O assistente não conseguiu responder agora. Tente de novo.", _motivo(r)
        )
    return r.json()


def conversar(sistema: str, historico: list[Turno], ferramentas: Ferramentas) -> str:
    """A conversa inteira recomeça no modelo reserva, se for o caso: as
    assinaturas de pensamento de um modelo não valem no outro."""
    return _com_reserva(lambda modelo: _conversar(modelo, sistema, historico, ferramentas))


def _conversar(modelo: str, sistema: str, historico: list[Turno], ferramentas: Ferramentas) -> str:
    conteudos = [
        {"role": "user" if t.papel == "usuario" else "model", "parts": [{"text": t.texto}]}
        for t in historico
    ]
    corpo_base = {
        "systemInstruction": {"parts": [{"text": sistema}]},
        "tools": [{"functionDeclarations": DECLARACOES}],
    }

    for _ in range(MAX_RODADAS):
        resposta = _chamar({**corpo_base, "contents": conteudos}, modelo=modelo)
        candidatos = resposta.get("candidates") or []
        if not candidatos:
            bloqueio = (resposta.get("promptFeedback") or {}).get("blockReason")
            raise ChatIndisponivel(
                "O assistente não conseguiu responder a essa pergunta.",
                f"sem resposta do modelo{f' (bloqueio: {bloqueio})' if bloqueio else ''}",
            )
        conteudo = candidatos[0].get("content") or {}
        partes = conteudo.get("parts") or []
        chamadas = [p["functionCall"] for p in partes if "functionCall" in p]

        if not chamadas:
            texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))
            return texto.strip() or "Não encontrei uma resposta para isso."

        # A parte do modelo volta intacta (com as assinaturas de pensamento).
        conteudos.append({"role": "model", "parts": partes})
        respostas = []
        for chamada in chamadas:
            resultado = ferramentas.executar(chamada.get("name", ""), chamada.get("args") or {})
            parte = {"functionResponse": {"name": chamada.get("name", ""), "response": resultado}}
            if chamada.get("id"):
                parte["functionResponse"]["id"] = chamada["id"]
            respostas.append(parte)
        conteudos.append({"role": "user", "parts": respostas})

    return (
        "A pergunta exigiu consultas demais. Tente dividir em perguntas menores, "
        "ou dizer a obra e a disciplina."
    )



LEITURA = """Você está lendo o PDF de uma prancha de projeto de construção civil
({codigo}). Responda, em português, só com o que estiver no PDF: {pergunta}

Regras: seja literal e cite o que está escrito (notas, legendas, carimbo,
tabela de revisões). Se algo não estiver legível ou não aparecer, diga isso —
não complete por conta própria. Medidas e cotas: transcreva como estão e avise
quando a leitura for incerta."""


def ler_pdf(dados: bytes, pergunta: str, codigo: str) -> str:
    """Uma chamada à parte, com o PDF junto. Volta só o texto lido — o PDF não
    entra no resto da conversa, que ficaria pesada a cada pergunta seguinte."""
    resposta = _com_reserva(lambda modelo: _chamar(
        {
            "contents": [{
                "role": "user",
                "parts": [
                    {"inlineData": {
                        "mimeType": "application/pdf",
                        "data": base64.b64encode(dados).decode("ascii"),
                    }},
                    {"text": LEITURA.format(codigo=codigo, pergunta=pergunta)},
                ],
            }],
        },
        tempo=TEMPO_LEITURA_PDF,
        modelo=modelo,
    ))
    partes = ((resposta.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    texto = "".join(p.get("text", "") for p in partes if not p.get("thought")).strip()
    return texto or "Não foi possível ler o PDF."
