"""E-mail a cada 👎 no chat (TREELE, 21/10/2026).

A avaliação fica no banco de qualquer jeito; o e-mail é só para alguém ficar
sabendo no mesmo dia, sem precisar consultar. Vai para os endereços de
CHAT_AVISAR_AVALIACOES (hoje, só o estágio de projetos), não para os
administradores todos.

O comentário chega depois do voto (a pessoa clica 👎 e só então escreve), por
isso sai um segundo e-mail quando ele vem, com o mesmo assunto para cair na
mesma conversa.
"""

from sqlalchemy.orm import Session

from ..config import settings
from ..models import AvaliacaoChat, Obra
from . import email, email_modelo

LIMITE_RESPOSTA = 1500
LIMITE_PERGUNTA = 600


def _destinatarios() -> list[str]:
    return [e.strip() for e in settings.chat_avisar_avaliacoes.split(",") if e.strip()]


def _ultimo(conversa: list[dict], papel: str) -> str:
    return next((t.get("texto") or "" for t in reversed(conversa) if t.get("papel") == papel), "")


def _cortar(texto: str, limite: int) -> str:
    texto = texto.strip()
    return texto if len(texto) <= limite else texto[:limite].rstrip() + " […]"


def avisar(db: Session, avaliacao: AvaliacaoChat, *, so_comentario: bool = False) -> None:
    """Depois do commit. Nunca derruba a avaliação: e-mail que não sai fica
    só no banco, como já ficava."""
    destinos = _destinatarios()
    if not destinos or not settings.email_ligado or avaliacao.nota != -1:
        return
    conversa = avaliacao.conversa or []
    pergunta = _cortar(_ultimo(conversa, "usuario"), LIMITE_PERGUNTA)
    quem = avaliacao.usuario.nome if avaliacao.usuario else "Alguém"
    obra = db.get(Obra, avaliacao.obra_id) if avaliacao.obra_id else None

    if so_comentario:
        abertura = f"{quem} explicou o que estava errado na resposta marcada com 👎."
    else:
        abertura = f"{quem} marcou 👎 numa resposta do chat."
    blocos = [abertura, f"Pergunta:\n{pergunta}"]
    if avaliacao.comentario:
        blocos.append(f"O que estava errado:\n{avaliacao.comentario}")
    if not so_comentario:
        blocos.append(f"Resposta do chat:\n{_cortar(_ultimo(conversa, 'assistente'), LIMITE_RESPOSTA)}")
        if avaliacao.etapas:
            blocos.append("Etapas:\n" + "\n".join(f"· {e}" for e in avaliacao.etapas[:20]))
    modelo = " / ".join(x for x in (avaliacao.fornecedor, avaliacao.modelo) if x) or "?"
    blocos.append(
        f"Avaliação nº {avaliacao.id} · modelo {modelo}. Para corrigir, peça ao Claude Code: "
        f"\"leia os 👎 do chat e corrija\"."
    )
    texto = "\n\n".join(blocos)

    assunto = f"[Chat] 👎 nº {avaliacao.id} · {_cortar(pergunta.replace(chr(10), ' '), 70)}"
    link = settings.endereco_site
    nome_obra = f"{obra.codigo} · {obra.nome}" if obra else "Chat do acervo"
    html = email_modelo.html(
        tipo="avaliacao_chat",
        saudacao="Olá.",
        titulo="Comentário no 👎" if so_comentario else "Resposta do chat com problema",
        texto=texto,
        obra=nome_obra,
        cor_obra=obra.cor if obra else None,
        link=link,
        rotulo_botao="Abrir o sistema",
        cid_simbolo=email.CID_SIMBOLO,
    )
    email.enviar([
        email.Mensagem(
            para=para,
            assunto=assunto,
            texto=f"Olá.\n\n{texto}\n\n—\nTreèle Projetos · aviso automático, não responda este e-mail.",
            html=html,
        )
        for para in destinos
    ])
