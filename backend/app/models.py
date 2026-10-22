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
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .enums import (
    PapelObra,
    StatusArquivo,
    StatusRevisao,
    StatusSolicitacao,
    TipoArquivo,
    TipoNotificacao,
)


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
    # Perfil comercial: vê todas as obras, mas só a disciplina COM liberada para
    # obra, e só baixa. Nunca é administrador nem membro de equipe (deps.py).
    comercial: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
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

    # Engenheiro responsável pela obra. É quem responde pela obra perante a
    # equipe — papel diferente de "coordenador",
    # que é permissão. Pode haver vários coordenadores; responsável é um só.
    responsavel_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )

    # Logo do empreendimento. Guarda-se a chave no armazenamento, não a URL:
    # a URL é assinada e expira, e é gerada a cada leitura (ver logo_url).
    logo_chave: Mapped[str | None] = mapped_column(String(300), nullable=True)
    logo_tipo: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Cor de identidade do empreendimento (#rrggbb): pinta o cartão e o
    # cabeçalho da obra. Vazia, a tela usa o petróleo da treèle.
    cor: Mapped[str | None] = mapped_column(String(7), nullable=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    responsavel: Mapped["Usuario | None"] = relationship()
    membros: Mapped[list["ObraMembro"]] = relationship(
        back_populates="obra", cascade="all, delete-orphan"
    )
    documentos: Mapped[list["Documento"]] = relationship(back_populates="obra")

    @property
    def logo_url(self) -> str | None:
        """Endereço assinado do logo, para o navegador exibir numa <img>.

        A <img> não manda o token de sessão, então o endereço carrega a própria
        autorização — como os links de download. Não é público: logo de
        empreendimento que ainda não foi lançado é segredo comercial.
        """
        if not self.logo_chave or not self.logo_tipo:
            return None
        # Importado aqui: o modelo não deve depender do armazenamento para
        # ser carregado (migrações, scripts).
        from .services.storage import armazenamento

        return armazenamento.url_imagem(self.logo_chave, self.logo_tipo)


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
    solicitacoes: Mapped[list["SolicitacaoRevisao"]] = relationship(
        back_populates="documento",
        cascade="all, delete-orphan",
        order_by="SolicitacaoRevisao.criada_em.desc()",
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
    # Análise crítica (TREELE, 09/10/2026): a observação de quem liberou ou
    # reprovou — opcional ao liberar, obrigatória ao reprovar.
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    reprovada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reprovada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    # Vista marcada do modelo 3D que mostra o que reprovar (21/10/2026).
    vista_reprovacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("vistas_modelo.id", ondelete="SET NULL"), nullable=True
    )

    documento: Mapped["Documento"] = relationship(back_populates="revisoes")
    arquivos: Mapped[list["Arquivo"]] = relationship(
        back_populates="revisao", cascade="all, delete-orphan"
    )
    criada_por: Mapped["Usuario | None"] = relationship(foreign_keys=[criada_por_id])
    publicada_por: Mapped["Usuario | None"] = relationship(
        foreign_keys=[publicada_por_id]
    )
    reprovada_por: Mapped["Usuario | None"] = relationship(
        foreign_keys=[reprovada_por_id]
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


class SolicitacaoRevisao(Base):
    """Pedido de alteração num projeto liberado (TREELE, 02/10 e 05/10/2026).

    A obra pede, dizendo o que deve mudar (fotos e PDFs marcados são
    opcionais), e o coordenador autoriza ou recusa. O coordenador também
    autoriza direto, sem pedido — mudança que vem do escritório. Só com um
    pedido autorizado o documento aceita revisão nova; ele fecha quando quem
    libera a revisão nova para obra o marca como atendido (api/revisoes.publicar).
    """

    __tablename__ = "solicitacoes_revisao"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"), index=True
    )
    # A revisão liberada que estava valendo quando o pedido foi feito.
    revisao_id: Mapped[int | None] = mapped_column(
        ForeignKey("revisoes.id", ondelete="SET NULL"), nullable=True
    )
    descricao: Mapped[str] = mapped_column(Text)
    status: Mapped[StatusSolicitacao] = mapped_column(
        _enum(StatusSolicitacao, 16), default=StatusSolicitacao.aberta, index=True
    )
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    atendida_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    atendida_por_revisao_id: Mapped[int | None] = mapped_column(
        ForeignKey("revisoes.id", ondelete="SET NULL"), nullable=True
    )
    # Decisão do coordenador: autorizou (e quando), ou recusou com o motivo.
    decidida_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decidida_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    motivo_recusa: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Vista do modelo 3D de onde o pedido saiu (21/10/2026): a imagem marcada
    # vai como anexo, e a vista reabre a cena como estava.
    vista_id: Mapped[int | None] = mapped_column(
        ForeignKey("vistas_modelo.id", ondelete="SET NULL"), nullable=True
    )

    documento: Mapped["Documento"] = relationship(back_populates="solicitacoes")
    revisao: Mapped["Revisao | None"] = relationship(foreign_keys=[revisao_id])
    atendida_por_revisao: Mapped["Revisao | None"] = relationship(
        foreign_keys=[atendida_por_revisao_id]
    )
    criada_por: Mapped["Usuario | None"] = relationship(foreign_keys=[criada_por_id])
    decidida_por: Mapped["Usuario | None"] = relationship(foreign_keys=[decidida_por_id])
    anexos: Mapped[list["AnexoSolicitacao"]] = relationship(
        back_populates="solicitacao",
        cascade="all, delete-orphan",
        order_by="AnexoSolicitacao.id",
    )
    vista: Mapped["VistaModelo | None"] = relationship()
    # Projetistas que o coordenador marcou para a correção: avisados junto com
    # o da última revisão.
    mencionados: Mapped[list["Usuario"]] = relationship(
        secondary="mencoes_solicitacao", order_by="Usuario.nome"
    )


class AnexoSolicitacao(Base):
    """Foto ou PDF marcado que acompanha a solicitação. Sobe direto do
    navegador para o armazenamento, como os arquivos de projeto: foto de
    celular passa fácil do limite de corpo de requisição da hospedagem."""

    __tablename__ = "anexos_solicitacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitacao_id: Mapped[int] = mapped_column(
        ForeignKey("solicitacoes_revisao.id", ondelete="CASCADE"), index=True
    )
    nome_original: Mapped[str] = mapped_column(String(300))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(120))
    tamanho: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[StatusArquivo] = mapped_column(
        _enum(StatusArquivo, 16), default=StatusArquivo.pendente
    )
    enviado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    solicitacao: Mapped["SolicitacaoRevisao"] = relationship(back_populates="anexos")


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


class Notificacao(Base):
    """Aviso para uma pessoa: aparece no sininho do sistema e vai por e-mail.

    Uma linha por destinatário, para cada um marcar como lida por conta
    própria. O texto é gravado pronto — é o retrato do momento, como o
    registro de atividades: se o documento mudar de título depois, o aviso
    continua dizendo o que disse.
    """

    __tablename__ = "notificacoes"
    __table_args__ = (Index("ix_notificacoes_usuario_lida", "usuario_id", "lida_em"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    tipo: Mapped[TipoNotificacao] = mapped_column(_enum(TipoNotificacao))
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"))
    documento_id: Mapped[int | None] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"), nullable=True
    )
    # A revisão de que o aviso trata — evita avisar duas vezes da mesma
    # revisão enviada (um arquivo substituído não é revisão nova).
    revisao_id: Mapped[int | None] = mapped_column(
        ForeignKey("revisoes.id", ondelete="SET NULL"), nullable=True
    )
    titulo: Mapped[str] = mapped_column(String(300))
    texto: Mapped[str] = mapped_column(Text, default="")
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    lida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Quando o e-mail saiu. Vazio = e-mail desligado ou o envio falhou; o aviso
    # no sistema vale do mesmo jeito.
    email_enviado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    obra: Mapped["Obra"] = relationship()


class AvaliacaoChat(Base):
    """👍 ou 👎 numa resposta do chat do acervo (TREELE, 21/10/2026).

    A conversa não fica guardada no servidor — só a que alguém avaliou, para
    saber onde o assistente erra. Por isso a linha leva o retrato completo:
    a conversa até a resposta avaliada, as etapas e quem respondeu.
    """

    __tablename__ = "avaliacoes_chat"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    obra_id: Mapped[int | None] = mapped_column(
        ForeignKey("obras.id", ondelete="SET NULL"), nullable=True
    )
    # +1 (👍) ou -1 (👎).
    nota: Mapped[int] = mapped_column(Integer, index=True)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{"papel": "usuario" | "assistente", "texto": ...}], terminando na
    # resposta avaliada.
    conversa: Mapped[list] = mapped_column(JSON, default=list)
    etapas: Mapped[list] = mapped_column(JSON, default=list)
    fornecedor: Mapped[str | None] = mapped_column(String(20), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    usuario: Mapped["Usuario | None"] = relationship()


class VistaModelo(Base):
    """Uma vista do modelo 3D (TREELE, 21/10/2026), no espírito do BCF: quais
    modelos estavam na cena, a câmera, os cortes, os elementos selecionados
    (pelo GlobalId, que não muda entre conversões) e a imagem da tela com as
    marcações desenhadas por cima."""

    __tablename__ = "vistas_modelo"

    id: Mapped[int] = mapped_column(primary_key=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)
    titulo: Mapped[str] = mapped_column(String(200))
    # Ids dos arquivos IFC na cena, na ordem.
    arquivos: Mapped[list] = mapped_column(JSON, default=list)
    # {"posicao": [x, y, z], "alvo": [x, y, z]}
    camera: Mapped[dict] = mapped_column(JSON, default=dict)
    # [{"normal": [x, y, z], "ponto": [x, y, z]}]
    cortes: Mapped[list] = mapped_column(JSON, default=list)
    # {"<arquivo_id>": ["<GlobalId>", ...]}
    selecao: Mapped[dict] = mapped_column(JSON, default=dict)
    # Arquivos desligados na cena (visíveis = arquivos - ocultos).
    ocultos: Mapped[list] = mapped_column(JSON, default=list)
    imagem_key: Mapped[str] = mapped_column(String(500), unique=True)
    # 0 enquanto a imagem não chegou ao armazenamento.
    imagem_tamanho: Mapped[int] = mapped_column(BigInteger, default=0)
    # Só os desenhos, em fundo transparente (21/10/2026): reabrindo a vista, o
    # visualizador os põe na cena 3D, onde coincidem com a foto no ângulo em
    # que foram feitos.
    marcacoes_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    marcacoes_tamanho: Mapped[int] = mapped_column(BigInteger, default=0)
    criada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    criada_por: Mapped["Usuario | None"] = relationship()


class MencaoSolicitacao(Base):
    __tablename__ = "mencoes_solicitacao"
    __table_args__ = (UniqueConstraint("solicitacao_id", "usuario_id", name="uq_mencao"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitacao_id: Mapped[int] = mapped_column(
        ForeignKey("solicitacoes_revisao.id", ondelete="CASCADE"), index=True
    )
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))


class ConjuntoConflito(Base):
    """Um conjunto de teste de conflitos da obra (TREELE, 22/10/2026), no
    sentido do "clash set" do Navisworks e do Trimble Connect: o grupo A, o
    grupo B, o tipo de teste e a tolerância. Compartilhado pela equipe.

    `pronto` marca os conjuntos que vêm com o sistema (ex.:
    "instalacoes-estrutura"): qualquer pessoa da equipe os usa, e eles nascem
    na primeira rodada. Os montados à mão são do coordenador."""

    __tablename__ = "conjuntos_conflito"
    __table_args__ = (UniqueConstraint("obra_id", "pronto", name="uq_conjunto_pronto"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(80))
    pronto: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # {"a": {"disciplinas", "categorias", "excluir"}, "b": {...}, "modo",
    #  "tolerancia", "folga", "ignorarMesmoModelo"} — o formato da tela.
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RodadaConflito(Base):
    """Uma detecção registrada: quais modelos estavam na cena e o saldo."""

    __tablename__ = "rodadas_conflito"

    id: Mapped[int] = mapped_column(primary_key=True)
    conjunto_id: Mapped[int] = mapped_column(
        ForeignKey("conjuntos_conflito.id", ondelete="CASCADE"), index=True
    )
    arquivos: Mapped[list] = mapped_column(JSON, default=list)
    encontrados: Mapped[int] = mapped_column(Integer, default=0)
    novos: Mapped[int] = mapped_column(Integer, default=0)
    reabertos: Mapped[int] = mapped_column(Integer, default=0)
    resolvidos: Mapped[int] = mapped_column(Integer, default=0)
    feita_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    feita_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    feita_por: Mapped["Usuario | None"] = relationship()


class Conflito(Base):
    """Um conflito entre duas peças, que sobrevive às revisões (TREELE,
    22/10/2026): é reconhecido de uma rodada para outra pelo GlobalId da peça
    B e de alguma das peças A, que não mudam entre exportações do mesmo
    modelo.

    Situação, como no Navisworks: novo (apareceu nesta rodada), ativo
    (continua aparecendo), aprovado (aceito — o furo que o calculista previu)
    e resolvido (não aparece mais numa rodada com os dois modelos)."""

    __tablename__ = "conflitos"

    id: Mapped[int] = mapped_column(primary_key=True)
    conjunto_id: Mapped[int] = mapped_column(
        ForeignKey("conjuntos_conflito.id", ondelete="CASCADE"), index=True
    )
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), index=True, default="novo")
    tipo: Mapped[str] = mapped_column(String(14), default="interferencia")
    documento_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("documentos.id", ondelete="SET NULL"), nullable=True
    )
    documento_b_id: Mapped[int | None] = mapped_column(
        ForeignKey("documentos.id", ondelete="SET NULL"), nullable=True
    )
    revisao_a: Mapped[str] = mapped_column(String(10), default="")
    revisao_b: Mapped[str] = mapped_column(String(10), default="")
    categoria_a: Mapped[str] = mapped_column(String(60), default="")
    categoria_b: Mapped[str] = mapped_column(String(60), default="")
    nome_a: Mapped[str | None] = mapped_column(String(300), nullable=True)
    nome_b: Mapped[str | None] = mapped_column(String(300), nullable=True)
    guids_a: Mapped[list] = mapped_column(JSON, default=list)
    guid_b: Mapped[str] = mapped_column(String(40), index=True)
    centro: Mapped[list] = mapped_column(JSON, default=list)
    # {"min": [x, y, z], "max": [x, y, z]}
    caixa: Mapped[dict] = mapped_column(JSON, default=dict)
    medida: Mapped[float] = mapped_column(Float, default=0.0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    visto_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vista_id: Mapped[int | None] = mapped_column(
        ForeignKey("vistas_modelo.id", ondelete="SET NULL"), nullable=True
    )
    # Por que foi aprovado (obrigatório ao aprovar).
    justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    atualizado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    documento_a: Mapped["Documento | None"] = relationship(foreign_keys=[documento_a_id])
    documento_b: Mapped["Documento | None"] = relationship(foreign_keys=[documento_b_id])
    atualizado_por: Mapped["Usuario | None"] = relationship()
