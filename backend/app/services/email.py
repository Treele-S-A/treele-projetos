"""Envio de e-mail por SMTP.

SMTP, e não a API de um fornecedor, de propósito: o mesmo código serve o
Resend, o Microsoft 365 e o Google Workspace — trocar de serviço é trocar
variável de ambiente, não código.

O envio nunca derruba quem chamou. Um aviso que não saiu por e-mail continua
no sistema; uma liberação para obra que falhasse por causa do servidor de
e-mail seria muito pior que o e-mail perdido.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr

from ..config import settings

log = logging.getLogger("treele.email")

# Função de hospedagem tem tempo contado; servidor que não responde em 10 s
# não vai responder.
TEMPO_LIMITE = 10


@dataclass
class Mensagem:
    para: str
    assunto: str
    texto: str


def _conectar() -> smtplib.SMTP:
    contexto = ssl.create_default_context()
    if settings.email_smtp_porta == 465:
        conexao: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.email_smtp_host, 465, timeout=TEMPO_LIMITE, context=contexto
        )
    else:
        conexao = smtplib.SMTP(
            settings.email_smtp_host, settings.email_smtp_porta, timeout=TEMPO_LIMITE
        )
        conexao.starttls(context=contexto)
    conexao.login(settings.email_smtp_usuario, settings.email_smtp_senha)
    return conexao


def enviar(mensagens: list[Mensagem]) -> list[bool]:
    """Manda tudo numa conexão só. Devolve, na mesma ordem, o que saiu."""
    if not mensagens or not settings.email_ligado:
        return [False] * len(mensagens)
    try:
        conexao = _conectar()
    except (OSError, smtplib.SMTPException) as erro:
        # Só o tipo do erro e o servidor: a mensagem do SMTP às vezes ecoa o
        # usuário, e o log da hospedagem não é lugar para isso.
        log.error("E-mail: não conectou em %s (%s).", settings.email_smtp_host, type(erro).__name__)
        return [False] * len(mensagens)

    dominio = parseaddr(settings.email_remetente)[1].rpartition("@")[2] or None
    saiu = []
    with conexao:
        for m in mensagens:
            msg = EmailMessage()
            msg["From"] = settings.email_remetente
            msg["To"] = m.para
            msg["Subject"] = m.assunto
            msg["Message-ID"] = make_msgid(domain=dominio)
            msg.set_content(m.texto)
            try:
                conexao.send_message(msg)
                saiu.append(True)
            except (OSError, smtplib.SMTPException) as erro:
                log.error("E-mail: recusado (%s).", type(erro).__name__)
                saiu.append(False)
    return saiu
