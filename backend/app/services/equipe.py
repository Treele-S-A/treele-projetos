"""Equipe da obra: o que vale para todas as obras sem ninguém precisar cadastrar.

Todo administrador é coordenador de todas as obras (TREELE, 02/10/2026) —
inclusive as que forem criadas depois e os administradores que vierem
depois. O administrador já podia tudo em qualquer obra; ser coordenador de
fato (uma linha na equipe) é o que o faz aparecer na equipe, ser chamado de
coordenador na tela e entrar na lista de quem recebe as notificações.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import PapelObra
from ..models import Obra, ObraMembro, Usuario


def garantir_admins_coordenadores(
    db: Session, *, obra: Obra | None = None, usuario: Usuario | None = None
) -> int:
    """Põe cada administrador como coordenador de cada obra. Devolve quantos
    ajustes fez. Sem argumentos, confere tudo; com `obra` ou `usuario`, só
    aquela obra ou aquele administrador. Não faz commit."""
    admins = (
        [usuario]
        if usuario is not None
        else list(db.scalars(select(Usuario).where(Usuario.admin.is_(True))))
    )
    admins = [a for a in admins if a.admin and not a.comercial]
    obras = [obra] if obra is not None else list(db.scalars(select(Obra)))
    if not admins or not obras:
        return 0

    existentes = {
        (m.obra_id, m.usuario_id): m
        for m in db.scalars(
            select(ObraMembro).where(
                ObraMembro.usuario_id.in_([a.id for a in admins]),
                ObraMembro.obra_id.in_([o.id for o in obras]),
            )
        )
    }

    ajustes = 0
    for o in obras:
        for a in admins:
            membro = existentes.get((o.id, a.id))
            if membro is None:
                db.add(ObraMembro(obra_id=o.id, usuario_id=a.id, papel=PapelObra.coordenador))
                ajustes += 1
            elif membro.papel != PapelObra.coordenador:
                membro.papel = PapelObra.coordenador
                ajustes += 1
    if ajustes:
        db.flush()
    return ajustes
