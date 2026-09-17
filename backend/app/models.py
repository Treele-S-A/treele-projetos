"""Modelo de dados.

A hierarquia central é:

    Obra → Documento → Revisão → Arquivo(s)

O **Documento** é a entidade estável ("Planta de Forma – Pav. Tipo"): ele nasce
uma vez e nunca muda de código. A **Revisão** é o que evolui (R00, R01, R02…) e
carrega o status. Os **Arquivos** são os bytes daquela revisão — normalmente
mais de um, porque a regra de arquivo companheiro exige o DWG com o PDF plotado
e o RVT com o IFC exportado.

Separar Documento de Revisão é o que permite responder "qual é a última versão
liberada disto?" sem depender de ninguém ter nomeado a pasta direito.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .enums import PapelObra, StatusArquivo, StatusRevisao, TipoArquivo


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _enum(tipo, tamanho: int = 32):
    """Grava enums como texto — portável entre SQLite e Postgres."""
    return SAEnum(
        tipo,
        native_enum=False,
        length=tamanho,
        values_callable=lambda e: [m.value for m in e],
    )


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(190), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    admin: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    membros: Mapped[list["ObraMembro"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )


class Obra(Base):
    __tablename__ = "obras"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(200))
    cliente: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)

    # Regra de arquivo companheiro, verificada na hora de liberar para obra.
    # Ex.: {"dwg": ["pdf"], "rvt": ["ifc"]} — "não publico DWG sem o PDF plotado".
    regra_companheiro: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"dwg": ["pdf"], "rvt": ["ifc"]}
    )

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    membros: Mapped[list["ObraMembro"]] = relationship(
        back_populates="obra", cascade="all, delete-orphan"
    )
    documentos: Mapped[list["Documento"]] = relationship(back_populates="obra")


class Disciplina(Base):
    __tablename__ = "disciplinas"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(120))
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)


class Fase(Base):
    __tablename__ = "fases"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(120))
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)


class ObraMembro(Base):
    __tablename__ = "obra_membros"
    __table_args__ = (UniqueConstraint("obra_id", "usuario_id", name="uq_membro_obra"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"))
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE")
    )
    papel: Mapped[PapelObra] = mapped_column(_enum(PapelObra))

    obra: Mapped["Obra"] = relationship(back_populates="membros")
    usuario: Mapped["Usuario"] = relationship(back_populates="membros")


class PadraoNomenclatura(Base):
    """Padrão de nome de arquivo aceito no upload.

    `obra_id` nulo = padrão global, usado por obras que não definiram o seu.
    O template é legível ("{obra}-{disciplina}-{fase}-{prancha}-R{revisao}")
    e é compilado em regex por services/nomenclatura.py.
    """

    __tablename__ = "padroes_nomenclatura"

    id: Mapped[int] = mapped_column(primary_key=True)
    obra_id: Mapped[int | None] = mapped_column(
        ForeignKey("obras.id", ondelete="CASCADE"), nullable=True, index=True
    )
    nome: Mapped[str] = mapped_column(String(120))
    template: Mapped[str] = mapped_column(String(400))
    tokens: Mapped[dict] = mapped_column(JSON, default=dict)
    extensoes: Mapped[list] = mapped_column(
        JSON, default=lambda: ["dwg", "rvt", "pdf", "ifc"]
    )
    exemplo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Documento(Base):
    __tablename__ = "documentos"
    __table_args__ = (
        UniqueConstraint("obra_id", "codigo", name="uq_documento_obra_codigo"),
        Index("ix_documento_filtro", "obra_id", "disciplina_id", "fase_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"))
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id"))
    fase_id: Mapped[int] = mapped_column(ForeignKey("fases.id"))

    codigo: Mapped[str] = mapped_column(String(200), index=True)
    titulo: Mapped[str | None] = mapped_column(String(300), nullable=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )

    obra: Mapped["Obra"] = relationship(back_populates="documentos")
    disciplina: Mapped["Disciplina"] = relationship()
    fase: Mapped["Fase"] = relationship()
    revisoes: Mapped[list["Revisao"]] = relationship(
        back_populates="documento",
        cascade="all, delete-orphan",
        order_by="Revisao.ordem",
    )


class Revisao(Base):
    __tablename__ = "revisoes"
    __table_args__ = (
        UniqueConstraint("documento_id", "numero", name="uq_revisao_documento_numero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"), index=True
    )

    numero: Mapped[str] = mapped_column(String(8))
    # Valor numérico do `numero`, para ordenar e achar "a anterior" sem parsear
    # string ("02" → 2, "B" → 2). Ver services/nomenclatura.ordem_revisao.
    ordem: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[StatusRevisao] = mapped_column(
        _enum(StatusRevisao), default=StatusRevisao.em_revisao, index=True
    )

    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Preenchido na Fase 3 (diff automático). Fica aqui desde já para que a
    # interface e a API não precisem mudar quando aquilo entrar.
    descricao_ia: Mapped[str | None] = mapped_column(Text, nullable=True)

    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    publicada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    publicada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    obsoleta_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    documento: Mapped["Documento"] = relationship(back_populates="revisoes")
    arquivos: Mapped[list["Arquivo"]] = relationship(
        back_populates="revisao", cascade="all, delete-orphan"
    )
    criada_por: Mapped["Usuario | None"] = relationship(foreign_keys=[criada_por_id])
    publicada_por: Mapped["Usuario | None"] = relationship(
        foreign_keys=[publicada_por_id]
    )


class Arquivo(Base):
    __tablename__ = "arquivos"

    id: Mapped[int] = mapped_column(primary_key=True)
    revisao_id: Mapped[int] = mapped_column(
        ForeignKey("revisoes.id", ondelete="CASCADE"), index=True
    )

    nome_original: Mapped[str] = mapped_column(String(300))
    tipo: Mapped[TipoArquivo] = mapped_column(_enum(TipoArquivo, 16))
    status: Mapped[StatusArquivo] = mapped_column(
        _enum(StatusArquivo, 16), default=StatusArquivo.pendente
    )

    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(
        String(120), default="application/octet-stream"
    )
    tamanho: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    enviado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    enviado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )

    revisao: Mapped["Revisao"] = relationship(back_populates="arquivos")
    enviado_por: Mapped["Usuario | None"] = relationship()


class Evento(Base):
    """Trilha de auditoria — inclusive quem baixou o quê.

    Em discussão contratual sobre "a obra executou com projeto desatualizado",
    este log é a prova. Nunca é editado nem apagado pela aplicação.
    """

    __tablename__ = "eventos"
    __table_args__ = (Index("ix_evento_busca", "obra_id", "criado_em"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    obra_id: Mapped[int | None] = mapped_column(ForeignKey("obras.id"), nullable=True)

    acao: Mapped[str] = mapped_column(String(60), index=True)
    entidade: Mapped[str] = mapped_column(String(40))
    entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detalhes: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    usuario: Mapped["Usuario | None"] = relationship()
