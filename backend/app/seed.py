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

# Templates que este projeto já distribuiu como padrão global. Serve para
# distinguir "nunca foi mexido" de "o coordenador customizou".
TEMPLATES_JA_DISTRIBUIDOS = {
    "{obra}-{disciplina}-{fase}-{sequencial}-R{revisao}",
    PADRAO_INICIAL["template"],
}

DISCIPLINAS = [
    ("ARQ", "Arquitetura"),
    ("EST", "Estrutura"),
    ("FUN", "Fundação"),
    ("CON", "Contenção"),
    ("ESC", "Escoramento"),
    ("MUR", "Muros"),
    ("PAT", "Patamarização"),
    ("COB", "Cobertura"),
    ("ESQ", "Esquadria"),
    ("IMP", "Impermeabilização"),
    ("HID", "Hidrossanitário"),
    ("DRE", "Drenagem"),
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

# Em ordem cronológica de projeto, não na ordem em que foram ditadas: é essa a
# ordem útil num filtro de tela.
FASES = [
    ("EP", "Estudo Preliminar"),
    ("AP", "Ante-projeto"),
    ("PL", "Projeto Legal"),
    ("PA", "Projeto Aprovado"),
    ("PB", "Projeto Básico"),
    ("PE", "Projeto Executivo"),
    ("AB", "As-Built"),
]

# Códigos que este projeto já distribuiu e que a TREELE não usa (17/09/2026).
# São desativados, nunca apagados: documento antigo que aponte para eles
# continua válido e acessível; o que para é a entrada de arquivo novo.
#
# A lista é explícita de propósito. Desativar "tudo que não está em FASES"
# derrubaria também qualquer fase que um administrador tenha criado pela tela.
FASES_APOSENTADAS = {"LV", "EV"}


def _completar_catalogo(db: Session, modelo, itens: list[tuple[str, str]]) -> int:
    """Insere o que falta, sem tocar no que já existe.

    Complementar em vez de só popular banco vazio é o que permite acrescentar
    uma disciplina nova a uma instalação em uso: basta atualizar a lista acima.
    Códigos já cadastrados ficam como estão — inclusive os desativados, para
    não ressuscitar o que alguém tirou de circulação de propósito.
    """
    existentes = {r.codigo.upper(): r for r in db.scalars(select(modelo))}
    novos = 0
    for ordem, (codigo, nome) in enumerate(itens):
        atual = existentes.get(codigo.upper())
        if atual is None:
            db.add(modelo(codigo=codigo, nome=nome, ordem=ordem))
            novos += 1
        else:
            # `ordem` é só apresentação (a ordem do filtro na tela), então pode
            # ser realinhada com a lista canônica sem risco. Sem isto, códigos
            # acrescentados depois recebem posições que colidem com as antigas
            # e o filtro fica embaralhado. O nome acompanha pela mesma razão.
            atual.ordem = ordem
            atual.nome = nome
    return novos


def _aposentar(db: Session, modelo, codigos: set[str]) -> list[str]:
    """Desativa códigos que saíram do padrão. Nunca apaga."""
    if not codigos:
        return []
    desativados = []
    for item in db.scalars(select(modelo).where(modelo.codigo.in_(codigos))):
        # Manda para o fim da lista: sem isto o código aposentado guarda a
        # posição antiga e aparece intercalado nas telas que mostram inativos.
        item.ordem = 900
        if item.ativa:
            item.ativa = False
            desativados.append(item.codigo)
    return desativados


def semear(db: Session) -> None:
    novas_disciplinas = _completar_catalogo(db, Disciplina, DISCIPLINAS)
    novas_fases = _completar_catalogo(db, Fase, FASES)
    aposentadas = _aposentar(db, Fase, FASES_APOSENTADAS)
    if novas_disciplinas or novas_fases:
        print(
            f"catálogos: +{novas_disciplinas} disciplina(s), +{novas_fases} fase(s)",
            flush=True,
        )
    if aposentadas:
        print(f"fases desativadas: {', '.join(sorted(aposentadas))}", flush=True)

    global_ = db.scalar(
        select(PadraoNomenclatura).where(PadraoNomenclatura.obra_id.is_(None))
    )
    if global_ is None:
        db.add(PadraoNomenclatura(obra_id=None, ativo=True, **PADRAO_INICIAL))
    elif global_.template in TEMPLATES_JA_DISTRIBUIDOS:
        # O padrão global nunca foi editado por ninguém: ainda é um que nós
        # distribuímos. Pode ser atualizado com segurança. Se alguém tiver
        # customizado, o template não estará nesta lista e nada é tocado.
        for campo, valor in PADRAO_INICIAL.items():
            setattr(global_, campo, valor)
        print("padrão de nomenclatura global atualizado", flush=True)

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
