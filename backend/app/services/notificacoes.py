"""Quem é avisado de quê (TREELE, 02/10 e 05/10/2026).

- Revisão nova enviada (primeiro arquivo dela): os coordenadores da obra —
  administradores inclusive, porque são coordenadores de todas as obras.
- Pedido de revisão da obra: os coordenadores, que autorizam ou recusam.
- Revisão autorizada: o projetista que subiu a última revisão do documento,
  só ele. É aqui, e não no pedido, que o projetista fica sabendo.
- Pedido recusado: quem pediu.
- Revisão reprovada na análise crítica: quem a enviou (criou a revisão ou
  mandou arquivo dela), com a observação do coordenador.
- Revisão liberada para obra: as pessoas com papel "obra" — o único aviso
  que a obra recebe. Uma vez por revisão, nunca por arquivo; e na liberação,
  não no envio, porque antes de liberada a revisão nem aparece para a obra.

Quem fez a ação não é avisado dela. O aviso fica no sistema e vai por e-mail
quando o e-mail está configurado (services/email.py).
"""

from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..config import settings
from ..enums import PapelObra, StatusRevisao, TipoNotificacao
from ..models import Documento, Notificacao, ObraMembro, Revisao, SolicitacaoRevisao, Usuario
from . import email, email_modelo

TEXTO_MAX_NO_AVISO = 600


def _membros(db: Session, obra_id: int, papel: PapelObra) -> list[Usuario]:
    return list(
        db.scalars(
            select(Usuario)
            .join(ObraMembro, ObraMembro.usuario_id == Usuario.id)
            .where(
                ObraMembro.obra_id == obra_id,
                ObraMembro.papel == papel,
                Usuario.ativo.is_(True),
            )
        )
    )


def projetista_da_ultima(db: Session, documento: Documento) -> list[Usuario]:
    """Quem subiu a última revisão do documento, se tiver papel de projetista.

    "Última" é a mais recente que não foi cancelada — pode ser uma ainda em
    revisão: se o projetista já está mexendo na R02, é ele quem precisa saber
    do pedido feito sobre a R01. "Subiu" é quem criou a revisão ou enviou
    algum arquivo dela (PDF de um, DWG de outro).
    """
    validas = [r for r in documento.revisoes if r.status != StatusRevisao.cancelado]
    if not validas:
        return []
    ultima = max(validas, key=lambda r: (r.ordem, r.id))
    quem = {ultima.criada_por_id} | {a.enviado_por_id for a in ultima.arquivos}
    quem.discard(None)
    return [
        u for u in _membros(db, documento.obra_id, PapelObra.projetista) if u.id in quem
    ]


def _criar(
    db: Session,
    destinatarios: Iterable[Usuario],
    autor: Usuario,
    *,
    tipo: TipoNotificacao,
    documento: Documento,
    titulo: str,
    texto: str,
    revisao: Revisao | None = None,
) -> list[Notificacao]:
    vistos: set[int] = set()
    criadas = []
    for u in destinatarios:
        if u.id == autor.id or u.id in vistos or u.comercial:
            continue
        vistos.add(u.id)
        n = Notificacao(
            usuario_id=u.id,
            tipo=tipo,
            obra_id=documento.obra_id,
            documento_id=documento.id,
            revisao_id=revisao.id if revisao else None,
            titulo=titulo[:300],
            texto=texto,
        )
        db.add(n)
        criadas.append(n)
    db.flush()
    return criadas


def _nome_documento(documento: Documento) -> str:
    return f"{documento.codigo} — {documento.titulo}" if documento.titulo else documento.codigo


def _resumo(texto: str) -> str:
    texto = texto.strip()
    return texto if len(texto) <= TEXTO_MAX_NO_AVISO else texto[: TEXTO_MAX_NO_AVISO - 1] + "…"


def ao_solicitar(db: Session, solicitacao: SolicitacaoRevisao, autor: Usuario) -> list[Notificacao]:
    """Pedido de revisão da obra: os coordenadores decidem. Não faz commit."""
    documento = solicitacao.documento
    obra = documento.obra
    numero = solicitacao.revisao.numero if solicitacao.revisao else None
    return _criar(
        db, _membros(db, obra.id, PapelObra.coordenador), autor,
        tipo=TipoNotificacao.solicitacao_revisao,
        documento=documento,
        titulo=f"Revisão solicitada · {documento.codigo}",
        texto=(
            f"{autor.nome} pediu revisão "
            + (f"da R{numero} de " if numero else "de ")
            + f"{_nome_documento(documento)}, na obra {obra.codigo} · {obra.nome}.\n\n"
            + f"O que deve mudar:\n{_resumo(solicitacao.descricao)}\n\n"
            + "Autorize ou recuse na tela do documento."
        ),
    )


def ao_autorizar(db: Session, solicitacao: SolicitacaoRevisao, autor: Usuario) -> list[Notificacao]:
    """Revisão autorizada: o projetista da última revisão. Não faz commit."""
    documento = solicitacao.documento
    obra = documento.obra
    numero = solicitacao.revisao.numero if solicitacao.revisao else None
    pedido_da_obra = solicitacao.criada_por_id != autor.id and solicitacao.criada_por
    texto = (
        f"{autor.nome} autorizou a revisão "
        + (f"da R{numero} de " if numero else "de ")
        + f"{_nome_documento(documento)}, na obra {obra.codigo} · {obra.nome}"
        + (f", pedida por {solicitacao.criada_por.nome}" if pedido_da_obra else "")
        + f".\n\nO que deve mudar:\n{_resumo(solicitacao.descricao)}"
        + (
            "\n\nO pedido traz uma vista marcada do modelo 3D: veja a imagem e abra a "
            "vista na tela do documento."
            if solicitacao.vista_id
            else ""
        )
    )
    # Quem subiu a última revisão e os projetistas que o coordenador marcou.
    return _criar(
        db, [*projetista_da_ultima(db, documento), *solicitacao.mencionados], autor,
        tipo=TipoNotificacao.revisao_autorizada,
        documento=documento,
        titulo=f"Revisão autorizada · {documento.codigo}",
        texto=texto,
    )


def ao_recusar(db: Session, solicitacao: SolicitacaoRevisao, autor: Usuario) -> list[Notificacao]:
    """Pedido recusado: quem pediu. Não faz commit."""
    documento = solicitacao.documento
    obra = documento.obra
    quem_pediu = [solicitacao.criada_por] if solicitacao.criada_por else []
    return _criar(
        db, [u for u in quem_pediu if u.ativo], autor,
        tipo=TipoNotificacao.solicitacao_recusada,
        documento=documento,
        titulo=f"Revisão não autorizada · {documento.codigo}",
        texto=(
            f"{autor.nome} não autorizou a revisão que você pediu em "
            f"{_nome_documento(documento)}, na obra {obra.codigo} · {obra.nome}.\n\n"
            f"Motivo:\n{_resumo(solicitacao.motivo_recusa or '')}\n\n"
            f"Seu pedido:\n{_resumo(solicitacao.descricao)}"
        ),
    )


def ao_enviar_revisao(db: Session, revisao: Revisao, autor: Usuario) -> list[Notificacao]:
    """Revisão nova subiu: os coordenadores. Uma vez por revisão — arquivo
    seguinte ou substituído na mesma revisão não avisa de novo. Não faz commit."""
    ja_avisado = db.scalar(
        select(
            exists().where(
                Notificacao.revisao_id == revisao.id,
                Notificacao.tipo == TipoNotificacao.revisao_enviada,
            )
        )
    )
    if ja_avisado:
        return []
    documento = revisao.documento
    obra = documento.obra
    texto = (
        f"{autor.nome} enviou a R{revisao.numero} de {_nome_documento(documento)}, "
        f"na obra {obra.codigo} · {obra.nome}. Ela está em revisão: confira e libere "
        "para obra."
    )
    if revisao.descricao:
        texto += f"\n\nO que mudou:\n{_resumo(revisao.descricao)}"
    return _criar(
        db, _membros(db, obra.id, PapelObra.coordenador), autor,
        tipo=TipoNotificacao.revisao_enviada,
        documento=documento,
        revisao=revisao,
        titulo=f"R{revisao.numero} enviada · {documento.codigo}",
        texto=texto,
    )


def ao_liberar(
    db: Session, revisao: Revisao, autor: Usuario, substituidas: list[Revisao]
) -> list[Notificacao]:
    """Revisão liberada para obra. Não faz commit."""
    documento = revisao.documento
    obra = documento.obra
    texto = (
        f"A R{revisao.numero} de {_nome_documento(documento)} foi liberada para obra "
        f"na {obra.codigo} · {obra.nome}."
    )
    if substituidas:
        anteriores = ", ".join(f"R{r.numero}" for r in substituidas)
        texto += f" A {anteriores} deixa de valer."
    if revisao.descricao:
        texto += f"\n\nO que mudou:\n{_resumo(revisao.descricao)}"
    return _criar(
        db, _membros(db, obra.id, PapelObra.obra), autor,
        tipo=TipoNotificacao.revisao_liberada,
        documento=documento,
        revisao=revisao,
        titulo=f"R{revisao.numero} liberada para obra · {documento.codigo}",
        texto=texto,
    )


def ao_reprovar(db: Session, revisao: Revisao, autor: Usuario) -> list[Notificacao]:
    """Revisão reprovada: quem a enviou, com a observação. Não faz commit."""
    documento = revisao.documento
    obra = documento.obra
    quem = {revisao.criada_por_id} | {a.enviado_por_id for a in revisao.arquivos}
    quem.discard(None)
    destinatarios = list(
        db.scalars(select(Usuario).where(Usuario.id.in_(quem), Usuario.ativo.is_(True)))
    )
    return _criar(
        db, destinatarios, autor,
        tipo=TipoNotificacao.revisao_reprovada,
        documento=documento,
        revisao=revisao,
        titulo=f"R{revisao.numero} reprovada · {documento.codigo}",
        texto=(
            f"{autor.nome} reprovou a R{revisao.numero} de {_nome_documento(documento)}, "
            f"na obra {obra.codigo} · {obra.nome}, na análise crítica.\n\n"
            f"Observação:\n{_resumo(revisao.observacao or '')}\n\n"
            + (
                "A reprovação traz uma vista marcada do modelo 3D: abra-a na tela do documento.\n\n"
                if revisao.vista_reprovacao_id
                else ""
            )
            + "Envie a correção numa revisão nova."
        ),
    )


def link(n: Notificacao) -> str:
    return f"{settings.endereco_site}/documentos/{n.documento_id}"


def enviar_emails(db: Session, notificacoes: list[Notificacao]) -> None:
    """Depois do commit: o aviso já está salvo no sistema, saia o e-mail ou não.
    Grava quando cada e-mail saiu."""
    if not notificacoes or not settings.email_ligado:
        return
    mensagens = []
    for n in notificacoes:
        usuario = db.get(Usuario, n.usuario_id)
        saudacao = f"Olá, {usuario.nome.split()[0]}."
        # No HTML, o título é a prancha — o selo já diz o que aconteceu.
        documento = db.get(Documento, n.documento_id) if n.documento_id else None
        if documento is not None and documento.titulo:
            titulo, subtitulo = documento.titulo, documento.codigo
        elif documento is not None:
            titulo, subtitulo = documento.codigo, None
        else:
            titulo, subtitulo = n.titulo, None
        mensagens.append(
            email.Mensagem(
                para=usuario.email,
                assunto=f"[{n.obra.codigo}] {n.titulo}",
                texto=(
                    f"{saudacao}\n\n{n.texto}\n\n"
                    f"Abrir no sistema: {link(n)}\n\n"
                    "—\nTreèle Projetos · aviso automático, não responda este e-mail."
                ),
                html=email_modelo.html(
                    tipo=n.tipo.value,
                    saudacao=saudacao,
                    titulo=titulo,
                    subtitulo=subtitulo,
                    texto=n.texto,
                    obra=f"{n.obra.codigo} · {n.obra.nome}",
                    cor_obra=n.obra.cor,
                    link=link(n),
                    cid_simbolo=email.CID_SIMBOLO,
                ),
            )
        )
    agora = datetime.now(timezone.utc)
    for n, saiu in zip(notificacoes, email.enviar(mensagens)):
        if saiu:
            n.email_enviado_em = agora
    db.commit()
