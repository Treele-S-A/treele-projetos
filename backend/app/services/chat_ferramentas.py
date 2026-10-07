"""As ferramentas do chat do acervo (Fase 2): as consultas que a IA pode fazer.

A IA não lê o banco direto nem o conteúdo dos arquivos. Ela pede uma destas
consultas, e cada uma passa pelas MESMAS regras da tela — papel na obra,
status visíveis, disciplina do perfil comercial. Quem é da obra não descobre
pelo chat revisão em andamento; o comercial só vê COM liberado; ninguém vê
obra de que não participa. E como a resposta sai do banco, a IA não inventa
número de revisão — que é justamente o erro que não se pode cometer aqui.

Tudo é só leitura. O chat consulta; quem altera é a pessoa, na tela.

Ler o PDF de um projeto (07/10/2026) segue a regra do download: só abre o que
a pessoa poderia baixar, e cada leitura fica no registro de atividades.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import ContextoObra, montar_contexto, status_visiveis
from ..enums import StatusRevisao, StatusSolicitacao, TipoArquivo
from ..models import (
    Disciplina,
    Documento,
    Fase,
    Obra,
    ObraMembro,
    Revisao,
    SolicitacaoRevisao,
    Usuario,
)
from . import auditoria
from .storage import armazenamento

LIMITE_DOCUMENTOS = 40

ROTULO_STATUS = {
    "em_revisao": "Em revisão",
    "liberado_para_obra": "Liberado para obra",
    "obsoleto": "Obsoleto",
    "cancelado": "Cancelado",
}

# Declarações no formato do Gemini (Schema com tipos em maiúsculas).
DECLARACOES = [
    {
        "name": "listar_obras",
        "description": "Lista as obras que a pessoa pode ver, com código e nome.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "buscar_documentos",
        "description": (
            "Busca documentos (pranchas) e devolve a revisão atual de cada um. "
            "Sem obra, busca em todas as obras que a pessoa vê. Use os códigos do "
            "catálogo para disciplina e fase."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "obra": {"type": "STRING", "description": "Código da obra, ex.: TRE."},
                "disciplina": {"type": "STRING", "description": "Código, ex.: EST, ARQ, HID."},
                "fase": {"type": "STRING", "description": "Código, ex.: PE, EP, AB."},
                "status": {
                    "type": "STRING",
                    "enum": list(ROTULO_STATUS),
                    "description": "Status da revisão atual.",
                },
                "texto": {
                    "type": "STRING",
                    "description": "Trecho do código ou do título, ex.: 'térreo', 'A01'.",
                },
            },
        },
    },
    {
        "name": "detalhar_documento",
        "description": (
            "Histórico completo de um documento: revisões (quem enviou, quem "
            "liberou, o que mudou, arquivos) e solicitações de revisão."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "codigo": {"type": "STRING", "description": "Código exato, ex.: TRE-ARQ-PE-001."},
            },
            "required": ["codigo"],
        },
    },
    {
        "name": "resumo_da_obra",
        "description": (
            "Quantos documentos a obra tem por disciplina e por status da revisão "
            "atual, e quantas solicitações de revisão estão abertas. Bom para "
            "pendências: o que falta liberar, que disciplina não entregou."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {"obra": {"type": "STRING", "description": "Código da obra."}},
            "required": ["obra"],
        },
    },
    {
        "name": "liberacoes_recentes",
        "description": "Revisões liberadas para obra nos últimos dias, mais recentes primeiro.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "dias": {"type": "INTEGER", "description": "Quantos dias para trás (padrão 7)."},
                "obra": {"type": "STRING", "description": "Código da obra; sem ele, todas."},
            },
        },
    },
    {
        "name": "ler_projeto",
        "description": (
            "Abre o PDF de um documento e lê o que está nele: carimbo (título, "
            "escala, responsável, data), tabela de revisões da prancha, notas "
            "gerais, legendas, especificações, ambientes e elementos desenhados. "
            "Use quando a pergunta for sobre o CONTEÚDO da prancha, e não sobre "
            "status ou histórico. Sem revisão, lê a vigente."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "codigo": {"type": "STRING", "description": "Código exato, ex.: TRE-ARQ-PE-001."},
                "pergunta": {
                    "type": "STRING",
                    "description": "O que procurar no PDF, em português.",
                },
                "revisao": {"type": "STRING", "description": "Ex.: R01. Opcional."},
            },
            "required": ["codigo", "pergunta"],
        },
    },
    {
        "name": "listar_solicitacoes",
        "description": (
            "Solicitações de revisão (pedidos de alteração em projeto liberado), "
            "com o que deve mudar, quem pediu e a situação."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "obra": {"type": "STRING", "description": "Código da obra; sem ele, todas."},
                "situacao": {
                    "type": "STRING",
                    "enum": ["aberta", "autorizada", "atendida", "recusada"],
                    "description": "aberta = aguardando autorização do coordenador.",
                },
            },
        },
    },
]


class Ferramentas:
    """As consultas, presas à pessoa que pergunta."""

    def __init__(
        self,
        db: Session,
        usuario: Usuario,
        leitor: Callable[[bytes, str, str], str] | None = None,
    ):
        self.db = db
        self.usuario = usuario
        # Quem lê o PDF (chat_modelo.ler_pdf). Injetado: os testes trocam por um
        # leitor de mentira, e este módulo não depende do fornecedor de IA.
        self.leitor = leitor

    # ------------------------------------------------------------- obras

    def _obras_visiveis(self) -> list[Obra]:
        consulta = select(Obra).where(Obra.ativa.is_(True)).order_by(Obra.codigo)
        if not self.usuario.admin and not self.usuario.comercial:
            consulta = consulta.where(
                Obra.id.in_(
                    select(ObraMembro.obra_id).where(ObraMembro.usuario_id == self.usuario.id)
                )
            )
        return list(self.db.scalars(consulta))

    def _contexto(self, codigo: str) -> ContextoObra:
        obra = next(
            (o for o in self._obras_visiveis() if o.codigo.upper() == (codigo or "").strip().upper()),
            None,
        )
        if obra is None:
            raise LookupError(f"Obra '{codigo}' não encontrada entre as que você pode ver.")
        return montar_contexto(self.db, self.usuario, obra.id)

    def _contextos(self, codigo: str | None) -> list[ContextoObra]:
        if codigo:
            return [self._contexto(codigo)]
        saida = []
        for obra in self._obras_visiveis():
            try:
                saida.append(montar_contexto(self.db, self.usuario, obra.id))
            except HTTPException:
                continue
        return saida

    # ------------------------------------------------------------- execução

    def executar(self, nome: str, argumentos: dict[str, Any]) -> dict[str, Any]:
        """Roda a consulta pedida pela IA. Erro vira texto para ela explicar."""
        metodo = {
            "listar_obras": self.listar_obras,
            "buscar_documentos": self.buscar_documentos,
            "detalhar_documento": self.detalhar_documento,
            "resumo_da_obra": self.resumo_da_obra,
            "liberacoes_recentes": self.liberacoes_recentes,
            "listar_solicitacoes": self.listar_solicitacoes,
            "ler_projeto": self.ler_projeto,
        }.get(nome)
        if metodo is None:
            return {"erro": f"Consulta desconhecida: {nome}."}
        try:
            return metodo(**(argumentos or {}))
        except LookupError as erro:
            return {"erro": str(erro)}
        except TypeError:
            return {"erro": "Parâmetros inválidos para a consulta."}

    # ------------------------------------------------------------- consultas

    def listar_obras(self) -> dict[str, Any]:
        return {"obras": [{"codigo": o.codigo, "nome": o.nome} for o in self._obras_visiveis()]}

    def buscar_documentos(self, obra=None, disciplina=None, fase=None, status=None, texto=None):
        from ..api.documentos import _aplicar_filtros, _consulta_base  # evita import circular

        disciplina_id = fase_id = None
        if disciplina:
            d = self.db.scalar(select(Disciplina).where(Disciplina.codigo == disciplina.upper()))
            if d is None:
                return {"erro": f"Disciplina '{disciplina}' não existe no catálogo."}
            disciplina_id = d.id
        if fase:
            f = self.db.scalar(select(Fase).where(Fase.codigo == fase.upper()))
            if f is None:
                return {"erro": f"Fase '{fase}' não existe no catálogo."}
            fase_id = f.id
        status_enum = StatusRevisao(status) if status in ROTULO_STATUS else None

        documentos, total = [], 0
        for ctx in self._contextos(obra):
            consulta, atual = _consulta_base(ctx)
            consulta = _aplicar_filtros(
                consulta, atual, disciplina_id=disciplina_id, fase_id=fase_id,
                status_revisao=status_enum, tipo=None, busca=texto,
            ).where(atual.status.in_(status_visiveis(ctx)))
            total += self.db.scalar(
                select(func.count()).select_from(consulta.order_by(None).subquery())
            ) or 0
            for doc, rev in self.db.execute(
                consulta.order_by(Documento.codigo).limit(LIMITE_DOCUMENTOS)
            ).all():
                if len(documentos) < LIMITE_DOCUMENTOS:
                    documentos.append(self._resumo_documento(ctx, doc, rev))
        saida: dict[str, Any] = {"total": total, "documentos": documentos}
        if total > len(documentos):
            saida["aviso"] = f"Mostrando {len(documentos)} de {total}. Refine a busca."
        return saida

    def _resumo_documento(self, ctx: ContextoObra, doc: Documento, rev: Revisao) -> dict:
        return {
            "id": doc.id,
            "link": f"/documentos/{doc.id}",
            "obra": ctx.obra.codigo,
            "codigo": doc.codigo,
            "titulo": doc.titulo,
            "disciplina": doc.disciplina.codigo,
            "fase": doc.fase.codigo,
            "revisao_atual": f"R{rev.numero}",
            "status": ROTULO_STATUS[rev.status.value],
            "liberada_em": _data(rev.publicada_em),
        }

    def detalhar_documento(self, codigo: str):
        for ctx in self._contextos(None):
            doc = self.db.scalar(
                select(Documento).where(
                    Documento.obra_id == ctx.obra.id, Documento.codigo == codigo.strip().upper()
                )
            )
            if doc is None or not ctx.ve_disciplina(doc.disciplina.codigo):
                continue
            visiveis = status_visiveis(ctx)
            revisoes = [
                r for r in sorted(doc.revisoes, key=lambda r: r.ordem, reverse=True)
                if r.status in visiveis
            ]
            if not revisoes:
                continue
            saida = {
                "id": doc.id,
                "link": f"/documentos/{doc.id}",
                "obra": f"{ctx.obra.codigo} · {ctx.obra.nome}",
                "codigo": doc.codigo,
                "titulo": doc.titulo,
                "disciplina": f"{doc.disciplina.codigo} · {doc.disciplina.nome}",
                "fase": f"{doc.fase.codigo} · {doc.fase.nome}",
                "revisoes": [
                    {
                        "numero": f"R{r.numero}",
                        "status": ROTULO_STATUS[r.status.value],
                        "enviada_em": _data(r.criada_em),
                        "enviada_por": r.criada_por.nome if r.criada_por else None,
                        "liberada_em": _data(r.publicada_em),
                        "liberada_por": r.publicada_por.nome if r.publicada_por else None,
                        "o_que_mudou": r.descricao,
                        "arquivos": [a.nome_original for a in r.arquivos if a.status.value == "disponivel"],
                    }
                    for r in revisoes
                ],
            }
            if not self.usuario.comercial:
                saida["solicitacoes"] = [_solicitacao(s) for s in doc.solicitacoes]
            return saida
        return {"erro": f"Documento '{codigo}' não encontrado entre os que você pode ver."}

    def ler_projeto(self, codigo: str, pergunta: str, revisao: str | None = None):
        from ..api.arquivos import _conferir_leitura  # a mesma regra do download

        if self.leitor is None:
            return {"erro": "Leitura de PDF indisponível."}
        for ctx in self._contextos(None):
            doc = self.db.scalar(
                select(Documento).where(
                    Documento.obra_id == ctx.obra.id, Documento.codigo == codigo.strip().upper()
                )
            )
            if doc is None or not ctx.ve_disciplina(doc.disciplina.codigo):
                continue
            visiveis = status_visiveis(ctx)
            candidatas = [
                r for r in sorted(doc.revisoes, key=lambda r: r.ordem, reverse=True)
                if r.status in visiveis and r.status != StatusRevisao.cancelado
            ]
            if revisao:
                numero = revisao.strip().upper().removeprefix("R")
                candidatas = [r for r in candidatas if r.numero.upper() == numero]
            if not candidatas:
                return {"erro": f"Nenhuma revisão de {doc.codigo} que você possa ler"
                                + (f" com o número {revisao}." if revisao else ".")}
            rev = candidatas[0]
            pdfs = [
                a for a in rev.arquivos
                if a.tipo == TipoArquivo.pdf and a.status.value == "disponivel"
            ]
            if not pdfs:
                return {"erro": f"A R{rev.numero} de {doc.codigo} não tem PDF para ler."}
            arquivo = pdfs[0]
            try:
                aviso = _conferir_leitura(arquivo, ctx)
            except HTTPException as erro:
                return {"erro": erro.detail}
            limite = settings.chat_pdf_max_mb * 1024 * 1024
            if arquivo.tamanho > limite:
                return {"erro": (
                    f"O PDF {arquivo.nome_original} tem {arquivo.tamanho / 1048576:.0f} MB; o "
                    f"assistente lê até {settings.chat_pdf_max_mb} MB. Abra o arquivo no sistema."
                )}

            leitura = self.leitor(armazenamento.ler_bytes(arquivo.storage_key), pergunta, doc.codigo)
            # Fica no registro como qualquer leitura de arquivo.
            auditoria.registrar(
                self.db, acao="lido_pelo_assistente", entidade="arquivo",
                entidade_id=arquivo.id, usuario=self.usuario, obra_id=ctx.obra.id,
                detalhes={
                    "arquivo": arquivo.nome_original, "documento": doc.codigo,
                    "revisao": rev.numero, "status_revisao": rev.status.value,
                },
            )
            saida = {
                "link": f"/documentos/{doc.id}",
                "codigo": doc.codigo,
                "titulo": doc.titulo,
                "revisao_lida": f"R{rev.numero}",
                "status": ROTULO_STATUS[rev.status.value],
                "arquivo": arquivo.nome_original,
                "leitura": leitura,
                "lembrete": "Medidas e cotas lidas do desenho devem ser conferidas no PDF.",
            }
            if aviso:
                saida["aviso"] = aviso
            if len(pdfs) > 1:
                saida["outros_pdfs_nesta_revisao"] = [a.nome_original for a in pdfs[1:]]
            return saida
        return {"erro": f"Documento '{codigo}' não encontrado entre os que você pode ver."}

    def resumo_da_obra(self, obra: str):
        from ..api.documentos import _consulta_base

        ctx = self._contexto(obra)
        consulta, atual = _consulta_base(ctx)
        consulta = consulta.where(atual.status.in_(status_visiveis(ctx)))
        por_disciplina: dict[str, dict[str, int]] = {}
        for doc, rev in self.db.execute(consulta).all():
            chave = f"{doc.disciplina.codigo} · {doc.disciplina.nome}"
            linha = por_disciplina.setdefault(chave, {})
            rotulo = ROTULO_STATUS[rev.status.value]
            linha[rotulo] = linha.get(rotulo, 0) + 1
        saida: dict[str, Any] = {
            "obra": f"{ctx.obra.codigo} · {ctx.obra.nome}",
            "documentos_por_disciplina_e_status": por_disciplina,
        }
        if not self.usuario.comercial:
            saida["solicitacoes_aguardando_autorizacao"] = self.db.scalar(
                select(func.count(SolicitacaoRevisao.id))
                .join(Documento, SolicitacaoRevisao.documento_id == Documento.id)
                .where(
                    Documento.obra_id == ctx.obra.id,
                    SolicitacaoRevisao.status == StatusSolicitacao.aberta,
                )
            ) or 0
        return saida

    def liberacoes_recentes(self, dias=7, obra=None):
        dias = max(1, min(int(dias or 7), 120))
        desde = datetime.now(timezone.utc) - timedelta(days=dias)
        itens = []
        for ctx in self._contextos(obra):
            visiveis = status_visiveis(ctx)
            for rev, doc in self.db.execute(
                select(Revisao, Documento)
                .join(Documento, Revisao.documento_id == Documento.id)
                .where(
                    Documento.obra_id == ctx.obra.id,
                    Revisao.publicada_em >= desde,
                    Revisao.status.in_(visiveis),
                )
            ).all():
                if not ctx.ve_disciplina(doc.disciplina.codigo):
                    continue
                itens.append({
                    "link": f"/documentos/{doc.id}",
                    "obra": ctx.obra.codigo,
                    "codigo": doc.codigo,
                    "titulo": doc.titulo,
                    "revisao": f"R{rev.numero}",
                    "status_hoje": ROTULO_STATUS[rev.status.value],
                    "liberada_em": _data(rev.publicada_em),
                    "o_que_mudou": rev.descricao,
                })
        itens.sort(key=lambda i: i["liberada_em"] or "", reverse=True)
        return {"dias": dias, "total": len(itens), "liberacoes": itens[:LIMITE_DOCUMENTOS]}

    def listar_solicitacoes(self, obra=None, situacao=None):
        if self.usuario.comercial:
            return {"erro": "O perfil comercial não acompanha solicitações de revisão."}
        itens = []
        for ctx in self._contextos(obra):
            consulta = (
                select(SolicitacaoRevisao, Documento)
                .join(Documento, SolicitacaoRevisao.documento_id == Documento.id)
                .where(Documento.obra_id == ctx.obra.id)
                .order_by(SolicitacaoRevisao.criada_em.desc())
            )
            if situacao in {s.value for s in StatusSolicitacao}:
                consulta = consulta.where(SolicitacaoRevisao.status == StatusSolicitacao(situacao))
            for s, doc in self.db.execute(consulta).all():
                item = _solicitacao(s)
                item.update({"obra": ctx.obra.codigo, "codigo": doc.codigo,
                             "titulo": doc.titulo, "link": f"/documentos/{doc.id}"})
                itens.append(item)
        return {"total": len(itens), "solicitacoes": itens[:LIMITE_DOCUMENTOS]}


def _data(valor: datetime | None) -> str | None:
    return valor.strftime("%d/%m/%Y %H:%M") if valor else None


SITUACAO = {
    "aberta": "Aguardando autorização",
    "autorizada": "Autorizada",
    "atendida": "Atendida",
    "recusada": "Recusada",
}


def _solicitacao(s: SolicitacaoRevisao) -> dict:
    return {
        "situacao": SITUACAO[s.status.value],
        "o_que_deve_mudar": s.descricao,
        "pedida_por": s.criada_por.nome if s.criada_por else None,
        "pedida_em": _data(s.criada_em),
        "sobre_a_revisao": f"R{s.revisao.numero}" if s.revisao else None,
        "decidida_por": s.decidida_por.nome if s.decidida_por else None,
        "motivo_da_recusa": s.motivo_recusa,
        "atendida_pela": f"R{s.atendida_por_revisao.numero}" if s.atendida_por_revisao else None,
    }


def catalogo(db: Session) -> str:
    """Disciplinas e fases ativas, para o texto de instruções da IA."""
    disciplinas = ", ".join(
        f"{d.codigo}={d.nome}"
        for d in db.scalars(select(Disciplina).where(Disciplina.ativa.is_(True)).order_by(Disciplina.ordem))
    )
    fases = ", ".join(
        f"{f.codigo}={f.nome}"
        for f in db.scalars(select(Fase).where(Fase.ativa.is_(True)).order_by(Fase.ordem))
    )
    return f"Disciplinas: {disciplinas}.\nFases: {fases}."
