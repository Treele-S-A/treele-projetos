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
