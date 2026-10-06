"""Contratos de entrada e saída da API (Pydantic v2)."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .enums import (
    PapelObra,
    StatusArquivo,
    StatusRevisao,
    StatusSolicitacao,
    TipoArquivo,
    TipoNotificacao,
)

T = TypeVar("T")


class Modelo(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Pagina(BaseModel, Generic[T]):
    itens: list[T]
    total: int
    pagina: int
    por_pagina: int


# --------------------------------------------------------------------------
# Autenticação e usuários
# --------------------------------------------------------------------------


class LoginEntrada(BaseModel):
    email: EmailStr
    senha: str


class TokenSaida(BaseModel):
    token: str
    tipo: str = "bearer"
    expira_em_minutos: int


class UsuarioOut(Modelo):
    id: int
    nome: str
    email: EmailStr
    admin: bool
    comercial: bool = False
    ativo: bool


class UsuarioCriar(BaseModel):
    nome: str = Field(min_length=2, max_length=160)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)
    admin: bool = False
    comercial: bool = False


class SenhaAlterar(BaseModel):
    senha_atual: str
    senha_nova: str = Field(min_length=8, max_length=128)


class SenhaRedefinir(BaseModel):
    # No corpo, nunca na URL: endereço com query string vai para o log de
    # acesso da hospedagem, para o histórico do navegador e para proxies.
    senha_nova: str = Field(min_length=8, max_length=128)


# --------------------------------------------------------------------------
# Catálogos
# --------------------------------------------------------------------------


class DisciplinaOut(Modelo):
    id: int
    codigo: str
    nome: str
    ordem: int
    ativa: bool


class DisciplinaCriar(BaseModel):
    codigo: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9]+$")
    nome: str = Field(min_length=2, max_length=120)
    ordem: int = 0


class FaseOut(Modelo):
    id: int
    codigo: str
    nome: str
    ordem: int
    ativa: bool


class FaseCriar(BaseModel):
    codigo: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9]+$")
    nome: str = Field(min_length=2, max_length=120)
    ordem: int = 0


# --------------------------------------------------------------------------
# Obras
# --------------------------------------------------------------------------


class ObraCriar(BaseModel):
    codigo: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    nome: str = Field(min_length=2, max_length=200)
    cliente: str | None = None
    regra_companheiro: dict[str, list[str]] | None = None


class ObraAtualizar(BaseModel):
    nome: str | None = None
    cliente: str | None = None
    ativa: bool | None = None
    regra_companheiro: dict[str, list[str]] | None = None
    # 0 limpa o responsável; None (ausente) deixa como está.
    responsavel_id: int | None = None
    # "" limpa (volta ao petróleo); None (ausente) deixa como está.
    cor: str | None = Field(default=None, pattern=r"^(#[0-9a-fA-F]{6})?$")


class ObraOut(Modelo):
    id: int
    codigo: str
    nome: str
    cliente: str | None
    ativa: bool
    regra_companheiro: dict
    responsavel: UsuarioOut | None = None
    logo_url: str | None = None
    cor: str | None = None


class ObraComPapel(ObraOut):
    papel: PapelObra | None = None
    permissoes: list[str] = []


class MembroCriar(BaseModel):
    usuario_id: int
    papel: PapelObra


class MembroOut(Modelo):
    id: int
    usuario_id: int
    papel: PapelObra
    usuario: UsuarioOut


# --------------------------------------------------------------------------
# Nomenclatura
# --------------------------------------------------------------------------


class PadraoCriar(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    template: str = Field(min_length=3, max_length=400)
    tokens: dict[str, dict]
    extensoes: list[str] = ["dwg", "rvt", "pdf", "ifc"]
    exemplo: str | None = None


class PadraoOut(Modelo):
    id: int
    obra_id: int | None
    nome: str
    template: str
    tokens: dict
    extensoes: list
    exemplo: str | None
    ativo: bool


class ValidarNomeEntrada(BaseModel):
    nomes: list[str] = Field(min_length=1, max_length=200)


class NomeAnalisado(BaseModel):
    nome_arquivo: str
    valido: bool
    erros: list[str]
    codigo_documento: str | None = None
    disciplina: str | None = None
    fase: str | None = None
    revisao: str | None = None
    titulo: str | None = None
    tipo: TipoArquivo | None = None
    documento_existe: bool = False
    # Título que o documento já tem — a tela mostra, para quem envia a R03
    # confirmar que é a prancha certa.
    documento_titulo: str | None = None
    # Se o envio vai exigir título. Quem decide é o servidor, com a mesma
    # regra do envio; a tela só pergunta.
    precisa_titulo: bool = False
    revisao_existe: bool = False
    # Se o envio vai exigir "o que mudou": é o primeiro arquivo da revisão.
    precisa_descricao: bool = False
    # Status da revisão de destino, quando ela já existe. A tela de envio usa
    # isto para avisar que o arquivo será acrescentado a algo já liberado.
    revisao_status: StatusRevisao | None = None


class ValidarNomeSaida(BaseModel):
    padrao: PadraoOut
    resultados: list[NomeAnalisado]


# --------------------------------------------------------------------------
# Documentos e revisões
# --------------------------------------------------------------------------


class ArquivoOut(Modelo):
    id: int
    nome_original: str
    tipo: TipoArquivo
    status: StatusArquivo
    tamanho: int
    sha256: str | None
    content_type: str
    enviado_em: datetime
    enviado_por: UsuarioOut | None = None


class RevisaoOut(Modelo):
    id: int
    numero: str
    ordem: int
    status: StatusRevisao
    descricao: str | None
    descricao_ia: str | None
    criada_em: datetime
    publicada_em: datetime | None
    obsoleta_em: datetime | None
    criada_por: UsuarioOut | None = None
    publicada_por: UsuarioOut | None = None
    arquivos: list[ArquivoOut] = []


class RevisaoResumo(Modelo):
    id: int
    numero: str
    status: StatusRevisao
    publicada_em: datetime | None
    criada_em: datetime


class AnexoOut(Modelo):
    id: int
    nome_original: str
    content_type: str
    tamanho: int


class SolicitacaoOut(BaseModel):
    id: int
    descricao: str
    status: StatusSolicitacao
    criada_em: datetime
    criada_por: UsuarioOut | None = None
    # Revisão liberada sobre a qual o pedido foi feito, e a que o atendeu.
    revisao_numero: str | None = None
    atendida_em: datetime | None = None
    atendida_por_numero: str | None = None
    # Autorização ou recusa do coordenador.
    decidida_em: datetime | None = None
    decidida_por: UsuarioOut | None = None
    motivo_recusa: str | None = None
    anexos: list[AnexoOut] = []


class NotificacaoOut(BaseModel):
    id: int
    tipo: TipoNotificacao
    titulo: str
    texto: str
    criada_em: datetime
    lida: bool
    documento_id: int | None = None
    obra_codigo: str


class NotificacaoContagem(BaseModel):
    nao_lidas: int


class EmailTesteSaida(BaseModel):
    enviado: bool
    para: str
    remetente: str
    erro: str | None = None


class SolicitacaoCriar(BaseModel):
    descricao: str


class SolicitacaoRecusar(BaseModel):
    motivo: str


class AnexoIniciar(BaseModel):
    nome_arquivo: str = Field(min_length=1, max_length=300)
    tamanho: int = Field(ge=1)


class AnexoIniciarSaida(BaseModel):
    anexo_id: int
    url: str
    metodo: str
    headers: dict[str, str]


class DocumentoOut(Modelo):
    id: int
    codigo: str
    titulo: str | None
    obra_id: int
    disciplina: DisciplinaOut
    fase: FaseOut
    criado_em: datetime
    total_revisoes: int = 0
    revisao_atual: RevisaoResumo | None = None
    # Pedidos de alteração esperando o coordenador, e os já autorizados — as
    # marcas ao lado do status.
    solicitacoes_abertas: int = 0
    solicitacoes_autorizadas: int = 0


class DocumentoDetalhe(DocumentoOut):
    revisoes: list[RevisaoOut] = []
    # Montado à mão (services/solicitacoes.saida), nunca lido direto da relação
    # do documento: lá estão anexos ainda pendentes, e o comercial não vê
    # pedido nenhum. O alias aponta para um atributo que o modelo não tem.
    solicitacoes: list[SolicitacaoOut] = Field(
        default_factory=list, validation_alias="solicitacoes_montadas"
    )


class DocumentoAtualizar(BaseModel):
    titulo: str | None = None


# --------------------------------------------------------------------------
# Árvore do acervo (Obra → Disciplina → Fase → Tipo → Arquivos)
# --------------------------------------------------------------------------


class NoArvore(BaseModel):
    """Um nível da árvore. `tamanho` e `total` são a soma do que está abaixo."""

    chave: str
    codigo: str
    nome: str
    tamanho: int = 0
    total: int = 0
    atualizado_em: datetime | None = None


class NoTipo(NoArvore):
    """Só o resumo por formato. A árvore navega até a pasta; quem lista os
    arquivos é a tela da pasta. Mandar todos os nomes aqui seriam megabytes
    de JSON que nenhuma tela desenha."""

    tipo: TipoArquivo


class NoFase(NoArvore):
    tipos: list[NoTipo] = []


class NoDisciplina(NoArvore):
    fases: list[NoFase] = []


class CatalogoResumo(BaseModel):
    codigo: str
    nome: str


class PastaSaida(BaseModel):
    """Conteúdo de uma pasta: os documentos de uma disciplina numa fase.

    Vem com o histórico completo de cada documento — é o que a tela de pasta
    mostra, e é o motivo de existir um endpoint próprio em vez de N chamadas
    ao detalhe de documento.
    """

    obra_codigo: str
    obra_nome: str
    disciplina: CatalogoResumo
    fase: CatalogoResumo
    total: int
    documentos: list["DocumentoDetalhe"] = []


class ArvoreSaida(BaseModel):
    obra_codigo: str
    obra_nome: str
    tamanho: int = 0
    total: int = 0
    atualizado_em: datetime | None = None
    disciplinas: list[NoDisciplina] = []


class RevisaoAtualizar(BaseModel):
    descricao: str | None = None


class PublicarEntrada(BaseModel):
    descricao: str | None = None
    # Pedidos de revisão abertos que esta revisão atende, marcados por quem
    # libera. Fecham na liberação; os não marcados seguem abertos.
    solicitacoes_atendidas: list[int] = []


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------


class UploadIniciarEntrada(BaseModel):
    nome_arquivo: str
    tamanho: int = Field(ge=0)
    content_type: str = "application/octet-stream"
    descricao: str | None = None
    substituir: bool = False
    # Obrigatório só quando o documento ainda não tem título (novo, ou antigo
    # que ficou sem). Nos demais casos é ignorado — ver api/uploads.py.
    titulo: str | None = None


class UploadIniciarSaida(BaseModel):
    arquivo_id: int
    revisao_id: int
    documento_id: int
    url: str
    metodo: str
    headers: dict[str, str]
    direto: bool
    revisao_nova: bool
    documento_novo: bool


class ExclusaoObraPrevia(BaseModel):
    """O que some junto com a obra — a tela mostra antes de confirmar."""

    codigo: str
    nome: str
    documentos: int
    revisoes: int
    arquivos: int
    tamanho: int
    solicitacoes: int
    membros: int


class ExclusaoObraEntrada(BaseModel):
    # O código da obra digitado e a senha de quem exclui: as duas travas.
    confirmacao: str
    senha: str


class ExclusaoRevisaoSaida(BaseModel):
    # Revisão anterior que voltou a valer, quando a excluída era a liberada.
    restaurada: str | None
    # A excluída era a única revisão: o documento saiu do acervo junto.
    documento_excluido: bool


class UploadConfirmarSaida(BaseModel):
    arquivo: ArquivoOut
    revisao: RevisaoOut


class DownloadSaida(BaseModel):
    url: str
    nome_arquivo: str
    aviso: str | None = None


# --------------------------------------------------------------------------
# Auditoria
# --------------------------------------------------------------------------


class EventoOut(Modelo):
    id: int
    acao: str
    entidade: str
    entidade_id: int | None
    detalhes: dict
    ip: str | None
    criado_em: datetime
    usuario: UsuarioOut | None = None
