"""Dados iniciais: disciplinas, fases, padrão de nomenclatura e o primeiro admin.

Roda a cada inicialização, mas só cria o que ainda não existe — é seguro
executar várias vezes. Os catálogos abaixo são um ponto de partida para a
Fase 0; ajuste-os à realidade da TREELE antes de cadastrar a primeira obra
(ver docs/nomenclatura.md).
"""

import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Disciplina, Fase, PadraoNomenclatura, Usuario
from .security import gerar_hash_senha
from .services.nomenclatura import PADRAO_INICIAL

DISCIPLINAS = [
    ("ARQ", "Arquitetura"),
    ("EST", "Estrutura"),
    ("HID", "Hidrossanitário"),
    ("ELE", "Elétrica"),
    ("PCI", "Prevenção e Combate a Incêndio"),
    ("CLI", "Climatização"),
    ("TEL", "Telecomunicações e Cabeamento"),
    ("GAS", "Gás"),
    ("AUT", "Automação"),
    ("TOP", "Topografia"),
    ("TER", "Terraplenagem"),
    ("PAV", "Pavimentação"),
    ("URB", "Implantação e Urbanismo"),
    ("PAI", "Paisagismo"),
    ("INT", "Interiores"),
    ("COO", "Coordenação e Compatibilização"),
]

FASES = [
    ("LV", "Levantamento"),
    ("EV", "Estudo de Viabilidade"),
    ("EP", "Estudo Preliminar"),
    ("AP", "Anteprojeto"),
    ("PL", "Projeto Legal"),
    ("PB", "Projeto Básico"),
    ("PE", "Projeto Executivo"),
    ("AB", "As Built"),
]


def semear(db: Session) -> None:
    if not db.scalar(select(func.count()).select_from(Disciplina)):
        for ordem, (codigo, nome) in enumerate(DISCIPLINAS):
            db.add(Disciplina(codigo=codigo, nome=nome, ordem=ordem))

    if not db.scalar(select(func.count()).select_from(Fase)):
        for ordem, (codigo, nome) in enumerate(FASES):
            db.add(Fase(codigo=codigo, nome=nome, ordem=ordem))

    tem_padrao_global = db.scalar(
        select(PadraoNomenclatura.id).where(PadraoNomenclatura.obra_id.is_(None))
    )
    if not tem_padrao_global:
        db.add(PadraoNomenclatura(obra_id=None, ativo=True, **PADRAO_INICIAL))

    if not db.scalar(select(func.count()).select_from(Usuario)):
        senha = settings.admin_senha or secrets.token_urlsafe(12)
        db.add(
            Usuario(
                nome="Administrador",
                email=settings.admin_email.lower(),
                senha_hash=gerar_hash_senha(senha),
                admin=True,
            )
        )
        if not settings.admin_senha:
            print("\n" + "=" * 68)
            print("  PRIMEIRO ACESSO — anote agora, isto não será exibido de novo")
            print(f"  E-mail: {settings.admin_email}")
            print(f"  Senha:  {senha}")
            print("=" * 68 + "\n", flush=True)

    db.commit()
