"""A hora de quem usa o sistema: Brasília (TREELE, 04/11/2026).

O servidor (Vercel) roda em UTC. Sem converter, depois das 21h "hoje" já era
amanhã: o término marcado no cronograma, a data da ata em PDF, o horário da
lista mestra e as datas que o chat cita saíam um dia ou três horas à frente.

Deslocamento fixo, e não um fuso por nome: o Brasil não tem horário de verão
desde 2019, e assim não dependemos da base de fusos do sistema operacional, que
nem toda hospedagem traz.
"""

from datetime import date, datetime, timedelta, timezone

BRASILIA = timezone(timedelta(hours=-3), "BRT")


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def agora() -> datetime:
    return _agora_utc().astimezone(BRASILIA)


def hoje() -> date:
    return agora().date()


def local(valor: datetime) -> datetime:
    """O instante em Brasília. O SQLite devolve sem fuso, mas é UTC igual."""
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(BRASILIA)


def data_br(valor: datetime) -> str:
    return local(valor).strftime("%d/%m/%Y")


def data_hora_br(valor: datetime) -> str:
    return local(valor).strftime("%d/%m/%Y %H:%M")
