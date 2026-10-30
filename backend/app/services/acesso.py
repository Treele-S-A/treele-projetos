"""Tipo de acesso do usuário (TREELE, 30/10/2026), editável depois de criado.

Quatro tipos, os da planilha de cargos:

- **administrador**: vê e faz tudo; entra como coordenador em toda obra.
- **comercial**: todas as obras, só a disciplina COM liberada (ver deps).
- **todas_obras**: papel "obra" (equipe de campo: vê e baixa o liberado) em
  toda obra, inclusive nas criadas depois, sem precisar de equipe.
- **obra_especifica**: só as obras em que está na equipe; nas que entram por
  aqui, com papel "obra".

Trocar o tipo arruma a equipe junto, para não sobrar permissão do tipo
anterior — o administrador rebaixado, por exemplo, deixa de ser coordenador
das obras em que só estava por ser administrador.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import PapelObra
from ..models import Obra, ObraMembro, Usuario
from .equipe import garantir_admins_coordenadores

TIPOS = ("administrador", "comercial", "todas_obras", "obra_especifica")


def tipo_de(usuario: Usuario) -> str:
    if usuario.admin:
        return "administrador"
    if usuario.comercial:
        return "comercial"
    if usuario.todas_obras:
        return "todas_obras"
    return "obra_especifica"


class AcessoInvalido(ValueError):
    pass


def aplicar(db: Session, usuario: Usuario, tipo: str, obra_ids: list[int] | None = None) -> None:
    """Põe o usuário no tipo dado. `obra_ids` só vale para obra_especifica:
    as obras em que ele fica (as outras saem da equipe dele)."""
    if tipo not in TIPOS:
        raise AcessoInvalido("Tipo de acesso desconhecido.")
    era_admin = usuario.admin
    if era_admin and tipo != "administrador":
        restantes = db.scalar(
            select(Usuario.id).where(Usuario.admin.is_(True), Usuario.ativo.is_(True), Usuario.id != usuario.id).limit(1)
        )
        if restantes is None:
            raise AcessoInvalido("É preciso ficar pelo menos um administrador ativo.")

    usuario.admin = tipo == "administrador"
    usuario.comercial = tipo == "comercial"
    usuario.todas_obras = tipo == "todas_obras"
    membros = list(db.scalars(select(ObraMembro).where(ObraMembro.usuario_id == usuario.id)))

    if tipo == "administrador":
        db.flush()
        garantir_admins_coordenadores(db, usuario=usuario)
        return
    if tipo in ("comercial", "todas_obras"):
        # O tipo já dá o acesso a todas as obras; a equipe antiga só deixaria
        # sobrar papel (coordenador de quando era administrador).
        for m in membros:
            db.delete(m)
        return

    # obra_especifica
    membros_obras = {m.obra_id for m in membros}
    escolhidas = set(obra_ids) if obra_ids is not None else membros_obras
    existentes = set(db.scalars(select(Obra.id).where(Obra.id.in_(escolhidas))))
    if escolhidas - existentes:
        raise AcessoInvalido("Alguma das obras escolhidas não existe.")
    por_obra = {m.obra_id: m for m in membros}
    for obra_id, m in por_obra.items():
        if obra_id not in escolhidas:
            db.delete(m)
        elif era_admin:
            # Coordenador só por ser administrador: volta ao papel padrão.
            m.papel = PapelObra.obra
    for obra_id in escolhidas - por_obra.keys():
        db.add(ObraMembro(obra_id=obra_id, usuario_id=usuario.id, papel=PapelObra.obra))
