"""Trilha de auditoria.

Registrar download não é paranoia: quando aparece a discussão "a obra executou
com revisão vencida", esta tabela é quem responde.
"""

from fastapi import Request
from sqlalchemy.orm import Session

from ..models import Evento, Usuario


def _ip(request: Request | None) -> str | None:
    if request is None:
        return None
    encaminhado = request.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else None


def dispositivo(request: Request | None) -> str | None:
    """"Chrome no Windows", "Safari no iPhone": o bastante para reconhecer o aparelho."""
    if request is None:
        return None
    ua = request.headers.get("user-agent", "")
    if not ua:
        return None
    sistema = next((nome for chave, nome in (
        ("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"),
        ("Mac OS X", "Mac"), ("CrOS", "Chromebook"), ("Linux", "Linux"),
    ) if chave in ua), None)
    navegador = next((nome for chave, nome in (
        ("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung Internet"), ("Firefox/", "Firefox"),
        ("FxiOS", "Firefox"), ("CriOS", "Chrome"), ("Chrome/", "Chrome"), ("Safari/", "Safari"),
    ) if chave in ua), None)
    if not navegador and not sistema:
        return None
    return f"{navegador or 'Navegador'} no {sistema}" if sistema else navegador


def registrar(
    db: Session,
    *,
    acao: str,
    entidade: str,
    entidade_id: int | None = None,
    usuario: Usuario | None = None,
    obra_id: int | None = None,
    detalhes: dict | None = None,
    request: Request | None = None,
) -> Evento:
    evento = Evento(
        usuario_id=usuario.id if usuario else None,
        obra_id=obra_id,
        acao=acao,
        entidade=entidade,
        entidade_id=entidade_id,
        detalhes=detalhes or {},
        ip=_ip(request),
    )
    db.add(evento)
    return evento
