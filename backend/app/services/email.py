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
from .email_modelo import SIMBOLO

log = logging.getLogger("treele.email")

# Função de hospedagem tem tempo contado; servidor que não responde em 10 s
# não vai responder.
TEMPO_LIMITE = 10


# Identificador do símbolo dentro da mensagem: o HTML aponta para "cid:" + ele.
CID_SIMBOLO = "simbolo.treele@projetos"


@dataclass
class Mensagem:
    para: str
    assunto: str
    texto: str
    # Versão com a cara da Treèle (services/email_modelo.py). O texto vai
    # junto sempre, para quem lê sem HTML.
    html: str | None = None


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

    saiu = []
    with conexao:
        for m in mensagens:
            try:
                conexao.send_message(_montar(m))
                saiu.append(True)
            except (OSError, smtplib.SMTPException) as erro:
                log.error("E-mail: recusado (%s).", type(erro).__name__)
                saiu.append(False)
    return saiu


def _montar(m: Mensagem) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.email_remetente
    msg["To"] = m.para
    msg["Subject"] = m.assunto
    dominio = parseaddr(settings.email_remetente)[1].rpartition("@")[2] or None
    msg["Message-ID"] = make_msgid(domain=dominio)
    msg.set_content(m.texto)
    if m.html:
        msg.add_alternative(m.html, subtype="html")
        # O símbolo vai junto da parte HTML, e não por link: aparece mesmo no
        # programa que bloqueia imagem de fora.
        if SIMBOLO.is_file():
            msg.get_payload()[1].add_related(
                SIMBOLO.read_bytes(), maintype="image", subtype="png",
                cid=f"<{CID_SIMBOLO}>", filename="treele.png",
            )
    return msg


def _resposta_do_servidor(erro: smtplib.SMTPResponseException) -> str:
    texto = erro.smtp_error
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8", "replace")
    return f"{erro.smtp_code} {texto}"[:300]


def diagnosticar(m: Mensagem) -> str | None:
    """Manda um e-mail de teste e diz, em português, o que deu errado.

    None quando saiu. Só para a tela do administrador: diz o que o servidor
    respondeu, mas nunca repete a senha (o servidor também não a ecoa).
    """
    if not settings.email_ligado:
        return "E-mail desligado: EMAIL_SMTP_HOST não está definida."
    servidor = f"{settings.email_smtp_host}:{settings.email_smtp_porta}"
    try:
        conexao = _conectar()
    except smtplib.SMTPAuthenticationError:
        return (
            f"{servidor} recusou o usuário e a senha. No Resend, EMAIL_SMTP_USUARIO "
            "é a palavra resend e EMAIL_SMTP_SENHA é a API key inteira (começa com re_)."
        )
    except (OSError, smtplib.SMTPException) as erro:
        return f"Não conectou em {servidor} ({type(erro).__name__}). Confira host e porta."
    with conexao:
        try:
            conexao.send_message(_montar(m))
        except smtplib.SMTPSenderRefused as erro:
            return (
                f"Remetente recusado ({_resposta_do_servidor(erro)}). O domínio de "
                "EMAIL_REMETENTE precisa estar verificado no Resend."
            )
        except smtplib.SMTPResponseException as erro:
            resposta = _resposta_do_servidor(erro)
            # O Resend só reclama do domínio na entrega da mensagem, não no
            # remetente — a dica tem de sair daqui também.
            if "not verified" in resposta:
                return (
                    f"O domínio de EMAIL_REMETENTE ainda não está verificado no Resend "
                    f"({resposta}). Os registros DNS que o Resend mostra precisam estar "
                    "publicados no DNS do domínio e o domínio aparecer como Verified."
                )
            return f"O servidor recusou a mensagem: {resposta}"
        except (OSError, smtplib.SMTPException) as erro:
            return f"Falhou no envio ({type(erro).__name__})."
    return None
