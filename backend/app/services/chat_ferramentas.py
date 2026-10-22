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

import gzip
import json
import threading
import unicodedata
from collections import defaultdict
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
    "reprovado": "Reprovada",
}

# Declarações no formato do Gemini (Schema com tipos em maiúsculas). Consulta
# sem parâmetro vai SEM "parameters": objeto vazio o Gemini recusa, e a
# recusa derruba todas as perguntas. Opções fixas levam "format": "enum".
DECLARACOES = [
    {
        "name": "consultar_elementos",
        "description": (
            "Consulta elemento a elemento os modelos IFC (BIM) de uma obra, por QUALQUER "
            "parâmetro modelado: filtra (ex.: portas com 'Pset_DoorCommon/IsExternal' = Sim, "
            "paredes com 'Comentários' contendo 'externa'), agrupa (por pavimento, tipo ou um "
            "parâmetro), soma um parâmetro numérico e lista elementos. Use quando a pergunta "
            "depender de um parâmetro (resistência ao fogo, marca, fabricante, dimensão, "
            "ambiente, fck, se é externo) ou de elementos específicos. Antes de filtrar por um "
            "parâmetro cujo nome você não sabe, chame com mostrar_campos=true (com a categoria) "
            "para ver os nomes e exemplos de valores. Para somar áreas e volumes por material "
            "(reboco, concreto), prefira quantitativos_modelo."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "obra": {"type": "STRING", "description": "Código da obra, ex.: SER."},
                "disciplina": {"type": "STRING", "description": "Código da disciplina, ex.: ARQ. Opcional."},
                "categoria": {
                    "type": "STRING",
                    "description": "Trecho da categoria em português ou classe IFC, ex.: 'Porta', 'Parede', 'Janela', 'IfcSpace'.",
                },
                "pavimento": {"type": "STRING", "description": "Trecho do nome do pavimento, ex.: '3°', 'Tipo'."},
                "filtros": {
                    "type": "ARRAY",
                    "description": "Condições (todas valem juntas).",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "campo": {"type": "STRING", "description": "Trecho do nome do parâmetro, ex.: 'IsExternal', 'Marca', 'Comentários'."},
                            "operador": {
                                "type": "STRING",
                                "format": "enum",
                                "enum": ["contem", "igual", "diferente", "maior", "menor", "preenchido"],
                                "description": "Padrão: contem.",
                            },
                            "valor": {"type": "STRING", "description": "Valor ou trecho (números com ponto)."},
                        },
                        "required": ["campo"],
                    },
                },
                "agrupar_por": {
                    "type": "STRING",
                    "description": (
                        "'pavimento', 'tipo', 'categoria' ou trecho do nome de um parâmetro. Vários "
                        "separados por vírgula agrupam pela combinação, ex.: 'pavimento, tipo' — "
                        "prefira isso a uma consulta por pavimento."
                    ),
                },
                "somar": {"type": "STRING", "description": "Trecho do nome de um parâmetro numérico a somar, ex.: 'Cotas/Área'."},
                "listar": {"type": "BOOLEAN", "description": "Devolve até 50 elementos, com os parâmetros usados."},
                "mostrar_campos": {"type": "BOOLEAN", "description": "Mostra os parâmetros existentes e exemplos de valores."},
            },
            "required": ["obra"],
        },
    },
    {
        "name": "quantitativos_modelo",
        "description": (
            "Quantidades tiradas dos modelos IFC (BIM) de uma obra: áreas, volumes, "
            "comprimentos e contagens por tipo de elemento, material e pavimento. Use para "
            "perguntas como 'qual a área de reboco', 'volume de concreto das lajes', 'quantas "
            "portas', 'área de piso cerâmico'. Busque pelo material ou pelo tipo (ex.: "
            "'reboco', 'concreto', 'porta', 'drywall', 'cerâmica'). Sem busca, devolve o que "
            "o modelo tem (categorias, tipos e materiais), para escolher a busca certa. "
            "Comprimento de tubos, eletrodutos e dutos fica nos parâmetros: use "
            "consultar_elementos com somar."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "obra": {"type": "STRING", "description": "Código da obra, ex.: SER."},
                "busca": {
                    "type": "STRING",
                    "description": "Material, tipo ou categoria, ex.: 'reboco'. Palavras separadas: todas precisam aparecer.",
                },
                "disciplina": {"type": "STRING", "description": "Código da disciplina, ex.: ARQ. Opcional."},
                "pavimento": {"type": "STRING", "description": "Trecho do nome do pavimento, ex.: 'Tipo', '3°'. Opcional."},
            },
            "required": ["obra"],
        },
    },
    {
        "name": "listar_obras",
        "description": "Lista as obras que a pessoa pode ver, com código e nome.",
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
                    "format": "enum",
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
        "name": "consultar_conflitos",
        "description": (
            "Conflitos (interferências) entre disciplinas detectados no visualizador 3D: "
            "tubulação ou eletroduto atravessando pilar e viga, porta contra viga etc. "
            "Devolve quantos estão abertos por par de disciplinas, cada conjunto de teste "
            "com a última detecção (quando e por quem) e, com listar=true ou poucos "
            "resultados, os conflitos: peças, documentos, cota e quanto uma entra na outra. "
            "Use para 'quantos conflitos abertos na hidráulica', 'o que conflita com a viga "
            "V12', 'quais conflitos foram aprovados e por quê'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "obra": {"type": "STRING", "description": "Código da obra; sem ele, todas."},
                "disciplina": {
                    "type": "STRING",
                    "description": "Código de disciplina (HID, ELE, EST…): conflitos em que ela aparece, de qualquer lado.",
                },
                "situacao": {
                    "type": "STRING",
                    "format": "enum",
                    "enum": ["abertos", "novo", "ativo", "aprovado", "resolvido", "todos"],
                    "description": "Padrão: abertos (novo + ativo).",
                },
                "busca": {
                    "type": "STRING",
                    "description": "Trecho do nome de uma peça, ex.: 'V12', 'P33', 'esgoto'.",
                },
                "listar": {"type": "BOOLEAN", "description": "Devolve a lista dos conflitos (até 40)."},
            },
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
                    "format": "enum",
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
        etapa: Callable[[str], None] | None = None,
    ):
        self.db = db
        self.usuario = usuario
        # Quem lê o PDF (chat_modelo.ler_pdf). Injetado: os testes trocam por um
        # leitor de mentira, e este módulo não depende do fornecedor de IA.
        self.leitor = leitor
        # Quem mostra na tela o que o assistente está fazendo (21/10/2026):
        # cada consulta, o resultado dela e o que a IA diz entre uma e outra.
        self.etapa = etapa

    def anunciar(self, texto: str) -> None:
        if self.etapa and texto and texto.strip():
            self.etapa(texto.strip())

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
            "quantitativos_modelo": self.quantitativos_modelo,
            "consultar_elementos": self.consultar_elementos,
            "consultar_conflitos": self.consultar_conflitos,
        }.get(nome)
        if metodo is None:
            return {"erro": f"Consulta desconhecida: {nome}."}
        self.anunciar(descrever(nome, argumentos or {}))
        try:
            resultado = metodo(**(argumentos or {}))
        except LookupError as erro:
            resultado = {"erro": str(erro)}
        except TypeError:
            resultado = {"erro": "Parâmetros inválidos para a consulta."}
        self.anunciar(resumir(resultado))
        return resultado

    # ------------------------------------------------------------- consultas

    def _modelos_ifc(self, obra: str, disciplina: str | None):
        """Os IFC da obra que a pessoa pode ler: o da revisão mais recente que
        ela vê, de cada documento. Devolve (contexto, [(documento, arquivo, aviso)])."""
        from ..api.arquivos import _conferir_leitura

        ctx = self._contexto(obra)
        consulta = select(Documento).where(Documento.obra_id == ctx.obra.id)
        if disciplina:
            consulta = consulta.join(Disciplina).where(Disciplina.codigo == disciplina.upper())
        visiveis = status_visiveis(ctx)
        saida = []
        for doc in self.db.scalars(consulta.order_by(Documento.codigo)):
            if not ctx.ve_disciplina(doc.disciplina.codigo):
                continue
            revisoes = sorted(
                (r for r in doc.revisoes if r.status in visiveis and r.status != StatusRevisao.cancelado),
                key=lambda r: r.ordem, reverse=True,
            )
            arquivo = next(
                (a for r in revisoes for a in r.arquivos
                 if a.tipo == TipoArquivo.ifc and a.status.value == "disponivel"),
                None,
            )
            if arquivo is None:
                continue
            try:
                aviso = _conferir_leitura(arquivo, ctx)
            except HTTPException:
                continue
            saida.append((doc, arquivo, aviso))
        return ctx, saida

    def _base_modelo(self, doc, arquivo, aviso) -> dict[str, Any]:
        base = {"documento": doc.codigo, "titulo": doc.titulo, "link": f"/documentos/{doc.id}",
                "revisao": f"R{arquivo.revisao.numero}",
                "status": ROTULO_STATUS[arquivo.revisao.status.value]}
        if aviso:
            base["aviso"] = aviso
        return base

    def consultar_elementos(self, obra: str, disciplina: str | None = None, categoria: str | None = None,
                            pavimento: str | None = None, filtros: list | None = None,
                            agrupar_por: str | None = None, somar: str | None = None,
                            listar: bool = False, mostrar_campos: bool = False):
        """Filtra, agrupa e soma no índice completo de cada IFC (21/10/2026)."""
        from ..api.arquivos import chave_indice

        ctx, modelos_ifc = self._modelos_ifc(obra, disciplina)
        if not modelos_ifc:
            return {"erro": f"Nenhum modelo IFC que você possa ver na obra {ctx.obra.codigo}"
                            + (f" na disciplina {disciplina.upper()}." if disciplina else ".")}
        modelos = []
        for doc, arquivo, aviso in modelos_ifc:
            base = self._base_modelo(doc, arquivo, aviso)
            chave = chave_indice(arquivo)
            indice = _ler_indice(chave)
            if indice is None:
                modelos.append({**base, "erro": "Este IFC ainda não tem índice de parâmetros (abra-o uma vez no 3D)."})
                continue
            auditoria.registrar(
                self.db, acao="lido_pelo_assistente", entidade="arquivo", entidade_id=arquivo.id,
                usuario=self.usuario, obra_id=ctx.obra.id,
                detalhes={"arquivo": arquivo.nome_original, "documento": doc.codigo,
                          "revisao": arquivo.revisao.numero, "consulta": "elementos"},
            )
            modelos.append({**base, **_consultar_indice(
                indice, categoria=categoria, pavimento=pavimento, filtros=filtros or [],
                agrupar_por=agrupar_por, somar=somar, listar=bool(listar), mostrar_campos=bool(mostrar_campos),
            )})
        return {
            "obra": ctx.obra.codigo,
            "modelos": modelos,
            "como_ler": (
                "Valores do que o projetista modelou, em m, m² e m³. Parâmetros que começam com "
                "'Tipo · ' vêm do tipo do elemento e valem para todos os elementos dele."
            ),
        }

    def quantitativos_modelo(self, obra: str, busca: str | None = None, disciplina: str | None = None,
                             pavimento: str | None = None):
        """Soma, no resumo de cada IFC da obra, o que bate com a busca (21/10/2026)."""
        from ..api.arquivos import chave_resumo

        ctx, modelos_ifc = self._modelos_ifc(obra, disciplina)
        termos = _normalizar(busca or "").split()
        filtro_pav = _normalizar(pavimento or "")
        modelos: list[dict[str, Any]] = []
        for doc, arquivo, aviso in modelos_ifc:
            existe, _ = armazenamento.info(chave_resumo(arquivo))
            base = self._base_modelo(doc, arquivo, aviso)
            if not existe:
                modelos.append({**base, "erro": "Este IFC ainda não tem resumo de quantitativos (abra-o uma vez no 3D)."})
                continue
            resumo = json.loads(armazenamento.ler_bytes(chave_resumo(arquivo)))
            auditoria.registrar(
                self.db, acao="lido_pelo_assistente", entidade="arquivo", entidade_id=arquivo.id,
                usuario=self.usuario, obra_id=ctx.obra.id,
                detalhes={"arquivo": arquivo.nome_original, "documento": doc.codigo,
                          "revisao": arquivo.revisao.numero, "consulta": "quantitativos", "busca": busca or ""},
            )
            modelos.append({**base, **_somar_resumo(resumo, termos, filtro_pav)})
        if not modelos:
            return {"erro": f"Nenhum modelo IFC que você possa ver na obra {ctx.obra.codigo}"
                            + (f" na disciplina {disciplina.upper()}." if disciplina else ".")}
        return {
            "obra": ctx.obra.codigo,
            "busca": busca or "",
            "modelos": modelos,
            "como_ler": (
                "Quantidades exportadas pelo programa de projeto, em m, m² e m³. Em parede, a "
                "'área lateral líquida' é a área de uma face, já sem as aberturas — numa parede "
                "de acabamento (reboco, pintura, cerâmica), é a área do revestimento. A 'área "
                "informada' é de elementos que vieram sem área nas quantidades do IFC: é o "
                "parâmetro 'Área' do programa de projeto (no Revit, uma face, sem as aberturas); "
                "some-a ao total e diga que veio por esse caminho."
            ),
        }

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

    def consultar_conflitos(self, obra=None, disciplina=None, situacao=None, busca=None, listar=False):
        """Os conflitos guardados pelas detecções do visualizador 3D (22/10/2026),
        com as mesmas regras da tela: o comercial não vê."""
        from ..api.conflitos import conflitos_unicos
        from ..models import ConjuntoConflito, RodadaConflito

        if self.usuario.comercial:
            return {"erro": "O perfil comercial não acompanha conflitos entre disciplinas."}
        situacao = situacao or "abertos"
        disc = (disciplina or "").strip().upper()
        termo = _normalizar(busca or "")
        obras = []
        for ctx in self._contextos(obra):
            todos = conflitos_unicos(self.db, ctx.obra.id)
            conjuntos = list(self.db.scalars(
                select(ConjuntoConflito).where(ConjuntoConflito.obra_id == ctx.obra.id)
            ))
            if not todos and not conjuntos:
                if obra:
                    obras.append({"obra": ctx.obra.codigo, "aviso": "Nenhuma detecção de conflitos registrada nesta obra."})
                continue

            def disciplinas(c):
                return (c.documento_a.disciplina.codigo if c.documento_a else "?",
                        c.documento_b.disciplina.codigo if c.documento_b else "?")

            def serve(c):
                if disc and disc not in disciplinas(c):
                    return False
                if termo and termo not in _normalizar(f"{c.nome_a or ''} {c.nome_b or ''}"):
                    return False
                if situacao == "todos":
                    return True
                if situacao == "abertos":
                    return c.status in ("novo", "ativo")
                return c.status == situacao

            escolhidos = [c for c in todos if serve(c)]
            pares: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for c in todos:
                if disc and disc not in disciplinas(c):
                    continue
                pares[" × ".join(disciplinas(c))][c.status] += 1
            saida_conjuntos = []
            for cj in conjuntos:
                rodada = self.db.scalars(
                    select(RodadaConflito).where(RodadaConflito.conjunto_id == cj.id)
                    .order_by(RodadaConflito.feita_em.desc(), RodadaConflito.id.desc()).limit(1)
                ).first()
                saida_conjuntos.append({
                    "nome": cj.nome,
                    "ultima_deteccao": _data(rodada.feita_em) if rodada else None,
                    "feita_por": rodada.feita_por.nome if rodada and rodada.feita_por else None,
                    "encontrados_na_ultima": rodada.encontrados if rodada else None,
                })
            item: dict[str, Any] = {
                "obra": ctx.obra.codigo,
                "abertos": sum(1 for c in todos if c.status in ("novo", "ativo")
                               and (not disc or disc in disciplinas(c))),
                "por_par_de_disciplinas": {k: dict(v) for k, v in sorted(pares.items())},
                "conjuntos": saida_conjuntos,
                "encontrados": len(escolhidos),
            }
            if listar or len(escolhidos) <= 15:
                item["conflitos"] = [_conflito(c) for c in sorted(
                    escolhidos, key=lambda c: (c.centro[1] if c.centro else 0))[:40]]
                if len(escolhidos) > 40:
                    item["aviso"] = f"Mostrando 40 de {len(escolhidos)}. Refine por disciplina ou busca."
            obras.append(item)
        if not obras:
            return {"conflitos_obras": [], "aviso": "Nenhuma detecção de conflitos registrada nas suas obras."}
        return {
            "conflitos_obras": obras,
            "como_ler": (
                "Conflitos achados pela detecção do visualizador 3D (botão Conflitos), na última vez "
                "que alguém a rodou — diga quando. Situação: novo (apareceu na última detecção), ativo "
                "(continua), aprovado (aceito pelo coordenador, com justificativa) e resolvido (sumiu "
                "numa detecção com os dois modelos). 'entra_cm' é quanto uma peça entra na outra "
                "(estimado); 'cota_m' é a altura na cena. Para atualizar, rodar Detectar de novo no 3D."
            ),
        }

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


# As categorias IFC como a tela mostra (frontend/src/modelo3d/resumo-ifc.ts).
CATEGORIAS_IFC = {
    "IFCBEAM": "Viga", "IFCCOLUMN": "Pilar", "IFCSLAB": "Laje / piso", "IFCWALL": "Parede",
    "IFCWALLSTANDARDCASE": "Parede", "IFCDOOR": "Porta", "IFCWINDOW": "Janela",
    "IFCMEMBER": "Perfil / montante", "IFCFOOTING": "Fundação", "IFCSTAIR": "Escada",
    "IFCFLOWSEGMENT": "Tubo / duto", "IFCFLOWFITTING": "Conexão", "IFCFLOWTERMINAL": "Terminal",
    "IFCFLOWCONTROLLER": "Registro / válvula", "IFCPIPESEGMENT": "Tubo", "IFCPIPEFITTING": "Conexão",
    "IFCDUCTSEGMENT": "Duto", "IFCCABLECARRIERSEGMENT": "Eletrocalha / eletroduto",
    "IFCBUILDINGELEMENTPROXY": "Outro elemento",
}


def _categoria(codigo: str) -> str:
    return CATEGORIAS_IFC.get((codigo or "").upper(), (codigo or "").upper().replace("IFC", "").title())


def _conflito(c) -> dict[str, Any]:
    disc_a = c.documento_a.disciplina.codigo if c.documento_a else None
    disc_b = c.documento_b.disciplina.codigo if c.documento_b else None
    saida = {
        "situacao": c.status,
        "disciplinas": f"{disc_a} × {disc_b}",
        "peca_a": f"{_categoria(c.categoria_a)}: {c.nome_a or 'sem nome'}",
        "peca_b": f"{_categoria(c.categoria_b)}: {c.nome_b or 'sem nome'}",
        "documento_a": f"{c.documento_a.codigo} R{c.revisao_a}" if c.documento_a else None,
        "documento_b": f"{c.documento_b.codigo} R{c.revisao_b}" if c.documento_b else None,
        "link_documento_a": f"/documentos/{c.documento_a_id}" if c.documento_a_id else None,
        "link_documento_b": f"/documentos/{c.documento_b_id}" if c.documento_b_id else None,
        "entra_cm" if c.tipo == "interferencia" else "distancia_cm": round(c.medida * 100, 1),
        "cota_m": round(c.centro[1], 2) if c.centro else None,
        "visto_em": _data(c.visto_em),
    }
    if c.justificativa:
        saida["justificativa"] = c.justificativa
    if c.vista_id:
        saida["link_vista"] = f"/modelos?vista={c.vista_id}"
    return saida


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


# ------------------------------------------------------------- etapas na tela


def descrever(nome: str, args: dict[str, Any]) -> str:
    """A consulta em português, para a tela mostrar enquanto ela roda."""
    def onde() -> str:
        partes = []
        if args.get("disciplina"):
            partes.append(f"de {args['disciplina']}")
        if args.get("status"):
            partes.append(f"com status {ROTULO_STATUS.get(args['status'], args['status'])}")
        if args.get("texto"):
            partes.append(f"com “{args['texto']}”")
        if args.get("fase"):
            partes.append(f"na fase {args['fase']}")
        if args.get("obra"):
            partes.append(f"na obra {args['obra']}")
        return (" " + " ".join(partes)) if partes else ""

    match nome:
        case "listar_obras":
            return "Vendo as obras que você acompanha"
        case "buscar_documentos":
            return f"Buscando documentos{onde()}"
        case "detalhar_documento":
            return f"Abrindo o histórico de {args.get('codigo', 'um documento')}"
        case "resumo_da_obra":
            return f"Resumindo a obra {args.get('obra', '')}".strip()
        case "liberacoes_recentes":
            dias = args.get("dias") or 7
            obra = f" na obra {args['obra']}" if args.get("obra") else ""
            return f"Vendo as liberações dos últimos {dias} dias{obra}"
        case "listar_solicitacoes":
            obra = f" da obra {args['obra']}" if args.get("obra") else ""
            return f"Consultando as solicitações de revisão{obra}"
        case "consultar_elementos":
            o_que = args.get("categoria") or "elementos"
            detalhes = []
            for f in args.get("filtros") or []:
                if isinstance(f, dict) and f.get("campo"):
                    detalhes.append(f"{f['campo']} {f.get('operador') or 'contem'} {f.get('valor') or ''}".strip())
            if args.get("agrupar_por"):
                detalhes.append(f"agrupado por {args['agrupar_por']}")
            if args.get("somar"):
                detalhes.append(f"somando {args['somar']}")
            if args.get("mostrar_campos"):
                detalhes.append("vendo os parâmetros")
            extra = f" ({'; '.join(detalhes)})" if detalhes else ""
            return f"Consultando {o_que} no modelo IFC da obra {args.get('obra', '')}{extra}".strip()
        case "quantitativos_modelo":
            busca = f" ({args['busca']})" if args.get("busca") else ""
            return f"Somando quantidades do modelo IFC{busca} na obra {args.get('obra', '')}".strip()
        case "consultar_conflitos":
            sit = args.get("situacao") or "abertos"
            extras = [x for x in (args.get("disciplina"), args.get("busca")) if x]
            mais = f" ({', '.join(extras)})" if extras else ""
            obra = f" na obra {args['obra']}" if args.get("obra") else ""
            return f"Consultando os conflitos {sit}{mais}{obra}"
        case "ler_projeto":
            rev = f" ({args['revisao']})" if args.get("revisao") else ""
            return f"Lendo o PDF de {args.get('codigo', 'uma prancha')}{rev}"
    return "Consultando o acervo"


def resumir(resultado: dict[str, Any]) -> str | None:
    """O que a consulta trouxe, em poucas palavras."""
    if "erro" in resultado:
        return f"Não deu certo: {resultado['erro']}"
    if "revisoes" in resultado:  # histórico de um documento
        n = len(resultado["revisoes"])
        return f"{n} revis{'ão' if n == 1 else 'ões'} no histórico"
    if "documentos" in resultado:
        n = resultado.get("total", len(resultado["documentos"]))
        return f"{n} documento{'' if n == 1 else 's'} encontrado{'' if n == 1 else 's'}"
    if "liberacoes" in resultado:
        n = resultado.get("total", 0)
        return f"{n} libera{'ção' if n == 1 else 'ções'} no período"
    if "solicitacoes" in resultado:
        n = resultado.get("total", 0)
        return f"{n} solicita{'ção' if n == 1 else 'ções'}"
    if "obras" in resultado:
        n = len(resultado["obras"])
        return f"{n} obra{'' if n == 1 else 's'}"
    if "modelos" in resultado:
        n = len(resultado["modelos"])
        return f"{n} modelo{'' if n == 1 else 's'} IFC consultado{'' if n == 1 else 's'}"
    if "conflitos_obras" in resultado:
        n = sum(o.get("encontrados", 0) for o in resultado["conflitos_obras"])
        return f"{n} conflito{'' if n == 1 else 's'} encontrado{'' if n == 1 else 's'}"
    if "leitura" in resultado:
        return f"PDF lido ({resultado.get('revisao_lida', '')})".replace(" ()", "")
    return None


# ------------------------------------------------------- quantitativos IFC

ROTULO_QUANTIDADE = {
    "NetSideArea": "area_lateral_liquida_m2",
    "GrossSideArea": "area_lateral_bruta_m2",
    "NetArea": "area_liquida_m2",
    "GrossArea": "area_bruta_m2",
    "Area": "area_m2",
    "GrossFootprintArea": "area_projecao_m2",
    "NetFootprintArea": "area_projecao_liquida_m2",
    "GrossCeilingArea": "area_forro_m2",
    # Elemento sem área nas quantidades do IFC: o parâmetro "Área" do programa
    # de projeto (no Revit, a área de uma face, sem as aberturas).
    "AreaInformada": "area_informada_m2",
    "NetVolume": "volume_liquido_m3",
    "GrossVolume": "volume_bruto_m3",
    "Volume": "volume_m3",
    "Length": "comprimento_m",
}
UNIDADE = {"area": "m2", "volume": "m3", "comprimento": "m", "contagem": "un", "peso": "kg"}
MAX_TIPOS = 30


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


def _rotulo(nome: str, grandeza: str) -> str | None:
    if nome in ROTULO_QUANTIDADE:
        return ROTULO_QUANTIDADE[nome]
    if grandeza == "comprimento":
        return None  # só o "Length" soma (larguras e alturas somadas não dizem nada)
    return f"{nome}_{UNIDADE.get(grandeza, '')}".rstrip("_")


# O resumo só tem as quantidades oficiais do IFC; tubo, eletroduto e conexão
# costumam ter o comprimento só nos parâmetros (no Revit, "Dimensions/Length"),
# e a cor ou o material só no tipo. Dois 👎 de 21/10/2026: o chat disse que não
# havia metragem de PVC marrom, e o índice tinha 4.147 m.
DICA_SEM_MEDIDA = (
    "Antes de dizer que o modelo não tem a medida ou o material, use consultar_elementos: "
    "mostrar_campos=true com a categoria (ex.: 'Tubo') mostra os parâmetros, e somar "
    "(ex.: 'Length') dá o total; material e cor costumam estar em parâmetros do tipo "
    "('Tipo · ...')."
)


def _somar_resumo(resumo: dict, termos: list[str], filtro_pav: str) -> dict[str, Any]:
    grandezas = resumo.get("grandezas", {})
    materiais = resumo.get("materiais", {})
    grupos = [
        g for g in resumo.get("grupos", [])
        if not filtro_pav or filtro_pav in _normalizar(g.get("pavimento") or "")
    ]
    if not termos:
        # Sem busca: o que há no modelo, para a IA escolher o que procurar.
        categorias: dict[str, int] = defaultdict(int)
        tipos: dict[str, int] = defaultdict(int)
        for g in grupos:
            categorias[g["categoria"]] += g["n"]
            tipos[f"{g['categoria']} · {g['tipo']}"] += g["n"]
        nomes_materiais = sorted({m.split(" (")[0] for ms in materiais.values() for m in ms})
        return {
            "elementos": sum(categorias.values()),
            "categorias": dict(sorted(categorias.items(), key=lambda x: -x[1])),
            "tipos_mais_comuns": [t for t, _ in sorted(tipos.items(), key=lambda x: -x[1])[:60]],
            "materiais": nomes_materiais[:120],
            "pavimentos": resumo.get("pavimentos", []),
        }

    def bate(g: dict) -> bool:
        texto = _normalizar(" ".join([g["categoria"], g["tipo"], *materiais.get(g["tipo"], [])]))
        return all(t in texto for t in termos)

    por_tipo: dict[tuple[str, str], dict[str, Any]] = {}
    por_pavimento: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    total: dict[str, float] = defaultdict(float)
    for g in filter(bate, grupos):
        chave = (g["categoria"], g["tipo"])
        t = por_tipo.setdefault(chave, {
            "categoria": g["categoria"], "tipo": g["tipo"],
            "materiais": materiais.get(g["tipo"], []), "elementos": 0, "quantidades": defaultdict(float),
        })
        t["elementos"] += g["n"]
        pav = g.get("pavimento") or "(sem pavimento)"
        por_pavimento[pav]["elementos"] += g["n"]
        for nome, valor in g["q"].items():
            rotulo = _rotulo(nome, grandezas.get(nome, ""))
            if rotulo is None:
                continue
            t["quantidades"][rotulo] += valor
            total[rotulo] += valor
            por_pavimento[pav][rotulo] += valor
    if not por_tipo:
        return {"encontrados": 0, "aviso": "Nada no modelo bate com a busca. Tente sem busca para ver os materiais e tipos.",
                "dica": DICA_SEM_MEDIDA}
    arred = lambda d: {k: round(v, 2) for k, v in d.items()}  # noqa: E731
    tipos = sorted(por_tipo.values(), key=lambda t: -t["elementos"])
    sem_medida = sum(1 for t in tipos if not t["quantidades"])
    return {
        "encontrados": len(tipos),
        "tipos": [{**t, "quantidades": arred(t["quantidades"])} for t in tipos[:MAX_TIPOS]],
        **({"aviso": f"Mostrando {MAX_TIPOS} de {len(tipos)} tipos; o total soma todos."} if len(tipos) > MAX_TIPOS else {}),
        **({"dica": f"{sem_medida} tipo(s) vieram sem medida no resumo. {DICA_SEM_MEDIDA}"} if sem_medida else {}),
        "total": arred(total),
        "por_pavimento": {p: arred(v) for p, v in por_pavimento.items()},
    }


# ------------------------------------------------------- índice completo IFC

# Índices lidos ficam na memória da função enquanto ela está quente: a
# segunda pergunta sobre o mesmo modelo não baixa nem descompacta de novo.
_INDICES: dict[str, dict] = {}
_TRAVA_INDICES = threading.Lock()
MAX_INDICES_NA_MEMORIA = 4
MAX_GRUPOS = 60
MAX_LISTA = 50


def _ler_indice(chave: str) -> dict | None:
    with _TRAVA_INDICES:
        if chave in _INDICES:
            return _INDICES[chave]
    if not armazenamento.info(chave)[0]:
        return None
    indice = json.loads(gzip.decompress(armazenamento.ler_bytes(chave)))
    indice["_campos_norm"] = [_normalizar(c) for c in indice["campos"]]
    with _TRAVA_INDICES:
        if len(_INDICES) >= MAX_INDICES_NA_MEMORIA:
            _INDICES.pop(next(iter(_INDICES)))
        _INDICES[chave] = indice
    return indice


def _campos_que_batem(indice: dict, texto: str) -> list[int]:
    """Índices dos campos cujo nome contém o texto; o nome exato do parâmetro
    (depois da barra) vem primeiro."""
    t = _normalizar(texto)
    if not t:
        return []
    achados = [i for i, c in enumerate(indice["_campos_norm"]) if t in c]
    return sorted(achados, key=lambda i: (indice["_campos_norm"][i].rsplit("/", 1)[-1] != t, len(indice["campos"][i])))


def _numero(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _consultar_indice(indice: dict, *, categoria, pavimento, filtros, agrupar_por, somar, listar,
                      mostrar_campos) -> dict[str, Any]:
    cats = [_normalizar(c) for c in indice["categorias"]]
    tipos, pavs, campos = indice["tipos"], indice["pavimentos"], indice["campos"]
    cat_ok = None
    if categoria:
        t = _normalizar(categoria)
        cat_ok = {i for i, c in enumerate(cats) if t in c}
        # Classe IFC também vale ("IfcDoor", "door").
        classe = [i for i, c in enumerate(indice["_campos_norm"]) if c == "atributos/classe ifc"]
    pav_ok = None
    if pavimento:
        t = _normalizar(pavimento)
        pav_ok = {i for i, p in enumerate(pavs) if t in _normalizar(p)}

    condicoes = []
    for f in filtros:
        if not isinstance(f, dict) or not f.get("campo"):
            continue
        ids = _campos_que_batem(indice, str(f["campo"]))
        if not ids:
            return {"encontrados": 0, "aviso": f"Nenhum parâmetro com '{f['campo']}' neste modelo. Use mostrar_campos."}
        condicoes.append((ids, str(f.get("operador") or "contem"), str(f.get("valor") or "")))

    def bate(campos_el: dict, ids, operador, valor) -> bool:
        presentes = [campos_el[str(i)] for i in ids if str(i) in campos_el]
        if operador == "preenchido":
            return bool(presentes)
        if not presentes:
            return operador == "diferente"
        alvo = _normalizar(valor)
        for v in presentes:
            if operador in ("maior", "menor"):
                a, b = _numero(v), _numero(valor)
                if a is not None and b is not None and (a > b if operador == "maior" else a < b):
                    return True
            elif operador == "igual" and _normalizar(str(v)) == alvo:
                return True
            elif operador == "diferente":
                return all(_normalizar(str(x)) != alvo for x in presentes)
            elif operador == "contem" and alvo in _normalizar(str(v)):
                return True
        return False

    escolhidos = []
    for el in indice["elementos"]:
        cat, tipo, pav, _guid, _nome, campos_el = el
        if cat_ok is not None and cat not in cat_ok:
            classe_el = next((campos_el.get(str(i)) for i in classe if str(i) in campos_el), "")
            if _normalizar(categoria) not in _normalizar(str(classe_el)):
                continue
        if pav_ok is not None and pav not in pav_ok:
            continue
        if all(bate(campos_el, *c) for c in condicoes):
            escolhidos.append(el)

    saida: dict[str, Any] = {"encontrados": len(escolhidos)}
    if not escolhidos:
        saida["aviso"] = "Nenhum elemento atende. Confira os nomes com mostrar_campos."
        return saida

    if mostrar_campos:
        conta: dict[int, int] = defaultdict(int)
        exemplos: dict[int, set] = defaultdict(set)
        for el in escolhidos:
            for k, v in el[5].items():
                i = int(k)
                conta[i] += 1
                if len(exemplos[i]) < 4:
                    exemplos[i].add(str(v)[:60])
        ordem = sorted(conta, key=lambda i: -conta[i])[:90]
        saida["campos"] = [{"campo": campos[i], "preenchido_em": conta[i], "exemplos": sorted(exemplos[i])} for i in ordem]
        return saida

    ids_somar = _campos_que_batem(indice, somar) if somar else []
    if somar and not ids_somar:
        saida["aviso"] = f"Nenhum parâmetro com '{somar}' para somar."

    def valor_somado(el) -> float | None:
        for i in ids_somar:
            n = _numero(el[5].get(str(i)))
            if n is not None:
                return n
        return None

    if ids_somar:
        nums = [n for n in map(valor_somado, escolhidos) if n is not None]
        saida["somado"] = {"campo": campos[ids_somar[0]], "total": round(sum(nums), 3), "elementos_com_valor": len(nums)}

    if agrupar_por:
        fixos = {
            "pavimento": lambda el: pavs[el[2]] if el[2] >= 0 else "(sem pavimento)",
            "tipo": lambda el: tipos[el[1]],
            "categoria": lambda el: indice["categorias"][el[0]],
        }
        partes, nomes = [], []
        for criterio in [c.strip() for c in agrupar_por.split(",") if c.strip()]:
            a = _normalizar(criterio)
            if a in fixos:
                partes.append(fixos[a])
                nomes.append(a)
                continue
            ids_grupo = _campos_que_batem(indice, criterio)
            nomes.append(campos[ids_grupo[0]] if ids_grupo else criterio)
            partes.append(lambda el, ids=ids_grupo: next(
                (str(el[5][str(i)]) for i in ids if str(i) in el[5]), "(vazio)"))
        nome_grupo = " · ".join(nomes)

        def chave(el):
            return " · ".join(f(el) for f in partes)
        grupos: dict[str, list] = defaultdict(lambda: [0, 0.0])
        for el in escolhidos:
            g = grupos[chave(el)]
            g[0] += 1
            n = valor_somado(el) if ids_somar else None
            if n is not None:
                g[1] += n
        ordenados = sorted(grupos.items(), key=lambda x: -x[1][0])
        saida["agrupado_por"] = nome_grupo
        saida["grupos"] = [
            {"valor": k, "elementos": v[0], **({"soma": round(v[1], 3)} if ids_somar else {})}
            for k, v in ordenados[:MAX_GRUPOS]
        ]
        if len(ordenados) > MAX_GRUPOS:
            saida["aviso_grupos"] = f"Mostrando {MAX_GRUPOS} de {len(ordenados)} grupos."

    if listar or not (agrupar_por or ids_somar):
        usados = sorted({i for c in condicoes for i in c[0][:2]} | set(ids_somar[:1]))
        lista = []
        for el in escolhidos[:MAX_LISTA]:
            item = {"nome": el[4], "tipo": tipos[el[1]], "pavimento": pavs[el[2]] if el[2] >= 0 else None}
            for i in usados:
                if str(i) in el[5]:
                    item[campos[i]] = el[5][str(i)]
            lista.append(item)
        saida["elementos"] = lista
        if len(escolhidos) > MAX_LISTA:
            saida["aviso_lista"] = f"Listando {MAX_LISTA} de {len(escolhidos)}."
    return saida
