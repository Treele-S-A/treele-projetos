"""A conversa com o Claude (Anthropic), pela Messages API (16/10/2026).

Mesmo ciclo do Gemini (chat_modelo.py): a IA pede consultas, o servidor roda
cada uma com as permissões de quem pergunta e devolve o resultado, a IA
responde com base nele. As ferramentas são as mesmas declarações, traduzidas
para o formato da Anthropic (JSON Schema em minúsculas).

Escolha entre os dois: ver `Settings.chat_fornecedor_ativo`. A rota não sabe
qual está em uso — chama `chat_modelo.conversar`, que repassa para cá.
"""

import base64
import json
import logging
import time
from typing import Any

import httpx

from ..config import settings
from .chat_ferramentas import DECLARACOES, Ferramentas
from .chat_modelo import (
    LEITURA,
    MAX_RODADAS,
    TEMPO_LEITURA_PDF,
    TEMPO_POR_CHAMADA,
    ChatIndisponivel,
    Sobrecarga,
    Turno,
)

log = logging.getLogger("treele.chat")

URL = "https://api.anthropic.com/v1/messages"
VERSAO_API = "2023-06-01"
MAX_TOKENS_RESPOSTA = 2048
# A leitura de um descritivo ou de uma tabela de prancha é longa: com 2048 ela
# saía cortada no meio (teste com o acervo real, 16/10/2026).
MAX_TOKENS_LEITURA = 4096
# Sobrecarga (529/500) ou limite por minuto (429) com espera curta: repete uma
# vez depois da pausa. Espera longa não cabe no tempo da função.
PAUSA_ANTES_DE_REPETIR = 2.0
ESPERA_MAXIMA_429 = 8.0


class LimiteDeTaxa(Sobrecarga):
    """Limite por minuto da conta (429). `espera` é o retry-after, em segundos."""

    def __init__(self, mensagem: str, detalhe: str | None = None, espera: float | None = None):
        super().__init__(mensagem, detalhe)
        self.espera = espera


def _esquema(no: Any) -> Any:
    """Schema do Gemini (tipos em maiúsculas, "format": "enum") → JSON Schema."""
    if isinstance(no, dict):
        saida = {}
        for chave, valor in no.items():
            if chave == "format" and valor == "enum":
                continue
            if chave == "type" and isinstance(valor, str):
                saida[chave] = valor.lower()
            else:
                saida[chave] = _esquema(valor)
        return saida
    if isinstance(no, list):
        return [_esquema(v) for v in no]
    return no


def ferramentas_claude() -> list[dict]:
    return [
        {
            "name": d["name"],
            "description": d["description"],
            "input_schema": _esquema(d.get("parameters") or {"type": "OBJECT", "properties": {}}),
        }
        for d in DECLARACOES
    ]


def _motivo(r: httpx.Response) -> str:
    """Tipo e mensagem do erro da Anthropic. A chave vai no cabeçalho, nunca
    no corpo da resposta."""
    try:
        erro = r.json().get("error", {})
        mensagem = f"{erro.get('type', '')}: {erro.get('message', '')}"
    except ValueError:
        mensagem = r.text
    return f"{r.status_code} {mensagem}"[:400]


def _chamar(corpo: dict, tempo: float = TEMPO_POR_CHAMADA) -> dict:
    cabecalhos = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": VERSAO_API,
        "content-type": "application/json",
    }
    if settings.anthropic_workspace_id.strip():
        cabecalhos["anthropic-workspace-id"] = settings.anthropic_workspace_id.strip()
    try:
        r = httpx.post(
            URL,
            headers=cabecalhos,
            json=corpo,
            timeout=tempo,
        )
    except httpx.HTTPError as erro:
        log.error("Chat: sem resposta do Claude (%s).", type(erro).__name__)
        raise ChatIndisponivel(
            "O assistente não respondeu a tempo. Tente de novo.", type(erro).__name__
        ) from erro
    if r.status_code == 429:
        try:
            espera = float(r.headers.get("retry-after", ""))
        except ValueError:
            espera = None
        raise LimiteDeTaxa(
            "Muitas perguntas ao mesmo tempo. Espere um minuto e tente de novo.",
            _motivo(r),
            espera,
        )
    if r.status_code in (401, 403):
        log.error("Chat: chave do Claude recusada (%s).", r.status_code)
        raise ChatIndisponivel(
            "O assistente está mal configurado (chave recusada).", _motivo(r)
        )
    if r.status_code in (500, 529):
        raise Sobrecarga(
            "O serviço de IA está sobrecarregado agora. Tente de novo em alguns minutos.",
            _motivo(r),
        )
    if r.status_code >= 400:
        motivo = _motivo(r)
        log.error("Chat: erro do Claude: %s", motivo)
        if "credit balance" in motivo.lower():
            raise ChatIndisponivel(
                "Os créditos do assistente acabaram. Avise o administrador do sistema.", motivo
            )
        raise ChatIndisponivel(
            "O assistente não conseguiu responder agora. Tente de novo.", motivo
        )
    resposta = r.json()
    uso = resposta.get("usage") or {}
    log.info(
        "Chat: %s entrada=%s saída=%s cache_lido=%s cache_gravado=%s",
        corpo.get("model"), uso.get("input_tokens"), uso.get("output_tokens"),
        uso.get("cache_read_input_tokens"), uso.get("cache_creation_input_tokens"),
    )
    return resposta


def _com_repeticao(fazer):
    """Uma tentativa e, diante de sobrecarga ou limite por minuto com espera
    curta, mais uma depois da pausa. Outro erro não se repete."""
    try:
        return fazer()
    except LimiteDeTaxa as erro:
        if erro.espera is not None and erro.espera > ESPERA_MAXIMA_429:
            raise
        log.warning("Chat: limite por minuto do Claude (%s).", erro.detalhe)
        time.sleep(min(erro.espera or PAUSA_ANTES_DE_REPETIR, ESPERA_MAXIMA_429))
    except Sobrecarga as erro:
        log.warning("Chat: Claude sobrecarregado (%s).", erro.detalhe)
        time.sleep(PAUSA_ANTES_DE_REPETIR)
    return fazer()


def _texto(resposta: dict) -> str:
    return "".join(b.get("text", "") for b in resposta.get("content") or [] if b.get("type") == "text")


def conversar(sistema: str, historico: list[Turno], ferramentas: Ferramentas) -> str:
    mensagens: list[dict] = [
        {"role": "user" if t.papel == "usuario" else "assistant", "content": t.texto}
        for t in historico
    ]
    corpo_base = {
        "model": settings.chat_modelo_claude,
        "max_tokens": MAX_TOKENS_RESPOSTA,
        # Ferramentas + instruções se repetem em toda rodada: o cache faz a
        # segunda rodada em diante custar um décimo nessa parte.
        "system": [{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}],
        "tools": ferramentas_claude(),
    }

    for _ in range(MAX_RODADAS):
        resposta = _com_repeticao(lambda: _chamar({**corpo_base, "messages": mensagens}))
        blocos = resposta.get("content") or []
        chamadas = [b for b in blocos if b.get("type") == "tool_use"]

        if not chamadas:
            if resposta.get("stop_reason") == "refusal":
                raise ChatIndisponivel(
                    "O assistente não conseguiu responder a essa pergunta.", "recusa do modelo"
                )
            return _texto(resposta).strip() or "Não encontrei uma resposta para isso."

        # A resposta do modelo volta intacta; os resultados vão juntos, na ordem.
        mensagens.append({"role": "assistant", "content": blocos})
        resultados = []
        for chamada in chamadas:
            resultado = ferramentas.executar(chamada.get("name", ""), chamada.get("input") or {})
            resultados.append({
                "type": "tool_result",
                "tool_use_id": chamada["id"],
                "content": json.dumps(resultado, ensure_ascii=False, default=str),
                **({"is_error": True} if "erro" in resultado else {}),
            })
        mensagens.append({"role": "user", "content": resultados})

    return (
        "A pergunta exigiu consultas demais. Tente dividir em perguntas menores, "
        "ou dizer a obra e a disciplina."
    )


def ler_pdf(dados: bytes, pergunta: str, codigo: str) -> str:
    """Uma chamada à parte, com o PDF junto; volta só o texto lido."""
    resposta = _com_repeticao(lambda: _chamar(
        {
            "model": settings.chat_modelo_claude,
            "max_tokens": MAX_TOKENS_LEITURA,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "document", "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(dados).decode("ascii"),
                    }},
                    {"type": "text", "text": LEITURA.format(codigo=codigo, pergunta=pergunta)},
                ],
            }],
        },
        tempo=TEMPO_LEITURA_PDF,
    ))
    return _texto(resposta).strip() or "Não foi possível ler o PDF."
