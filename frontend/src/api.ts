/** Cliente da API e tipos do domínio. */

const BASE = import.meta.env.VITE_API ?? "http://localhost:8000";
const CHAVE_TOKEN = "treele.token";

export function lerToken(): string | null {
  return localStorage.getItem(CHAVE_TOKEN);
}

export function gravarToken(token: string | null) {
  if (token) localStorage.setItem(CHAVE_TOKEN, token);
  else localStorage.removeItem(CHAVE_TOKEN);
}

/** Erro da API já normalizado: uma mensagem e, quando houver, a lista de causas. */
export class ErroApi extends Error {
  status: number;
  erros: string[];
  esperado?: string;
  exemplo?: string;

  constructor(status: number, mensagem: string, erros: string[] = []) {
    super(mensagem);
    this.status = status;
    this.erros = erros;
  }
}

function normalizar(status: number, corpo: unknown): ErroApi {
  const detalhe = (corpo as { detail?: unknown })?.detail ?? corpo;

  if (typeof detalhe === "string") return new ErroApi(status, detalhe);

  if (Array.isArray(detalhe)) {
    // Erro de validação do FastAPI.
    const erros = detalhe.map((d: { msg?: string }) => d?.msg ?? "Campo inválido.");
    return new ErroApi(status, "Alguns campos estão inválidos.", erros);
  }

  if (detalhe && typeof detalhe === "object") {
    const d = detalhe as { mensagem?: string; erros?: string[]; esperado?: string; exemplo?: string };
    const erro = new ErroApi(status, d.mensagem ?? "Não foi possível concluir.", d.erros ?? []);
    erro.esperado = d.esperado;
    erro.exemplo = d.exemplo;
    return erro;
  }

  return new ErroApi(status, "Não foi possível concluir.");
}

async function pedir<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const cabecalhos = new Headers(opcoes.headers);
  const token = lerToken();
  if (token) cabecalhos.set("Authorization", `Bearer ${token}`);
  if (opcoes.body && !cabecalhos.has("Content-Type")) {
    cabecalhos.set("Content-Type", "application/json");
  }

  let resposta: Response;
  try {
    resposta = await fetch(`${BASE}${caminho}`, { ...opcoes, headers: cabecalhos });
  } catch {
    throw new ErroApi(0, "Sem conexão com o servidor. Verifique se a API está no ar.");
  }

  // Tela aberta antes de uma atualização continua rodando o código antigo
  // contra o servidor novo — foi assim que o envio pediu "o que mudou" numa
  // tela que nem tinha o campo. O servidor carimba a versão; diferindo, avisa.
  const versaoServidor = resposta.headers.get("X-Versao");
  if (__VERSAO__ && versaoServidor && versaoServidor !== __VERSAO__) {
    window.dispatchEvent(new Event("treele:versao-nova"));
  }

  if (resposta.status === 401) {
    gravarToken(null);
    window.dispatchEvent(new Event("treele:sessao-expirada"));
    throw new ErroApi(401, "Sessão expirada. Entre novamente.");
  }

  if (!resposta.ok) {
    let corpo: unknown = null;
    try {
      corpo = await resposta.json();
    } catch {
      /* resposta sem corpo JSON */
    }
    throw normalizar(resposta.status, corpo);
  }

  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

export const api = {
  get: <T>(c: string) => pedir<T>(c),
  post: <T>(c: string, corpo?: unknown) =>
    pedir<T>(c, { method: "POST", body: corpo === undefined ? undefined : JSON.stringify(corpo) }),
  patch: <T>(c: string, corpo?: unknown) =>
    pedir<T>(c, { method: "PATCH", body: corpo === undefined ? undefined : JSON.stringify(corpo) }),
  put: <T>(c: string, corpo?: unknown) =>
    pedir<T>(c, { method: "PUT", body: corpo === undefined ? undefined : JSON.stringify(corpo) }),
  delete: <T>(c: string) => pedir<T>(c, { method: "DELETE" }),
  /** Imagem crua no corpo, com o tipo dela — não é JSON. */
  enviarImagem: <T>(c: string, imagem: Blob) =>
    pedir<T>(c, { method: "PUT", body: imagem, headers: { "Content-Type": imagem.type } }),
  base: BASE,
};

/* ------------------------------------------------------------------ tipos */

export type StatusRevisao =
  | "em_revisao"
  | "liberado_para_obra"
  | "obsoleto"
  | "cancelado";

export type TipoArquivo = "dwg" | "rvt" | "pdf" | "ifc" | "outro";
export type PapelObra = "coordenador" | "projetista" | "obra";

export interface Usuario {
  id: number;
  nome: string;
  email: string;
  admin: boolean;
  /** Perfil comercial: todas as obras, só a disciplina COM liberada, só baixa. */
  comercial: boolean;
  ativo: boolean;
}

export interface Obra {
  id: number;
  codigo: string;
  nome: string;
  cliente: string | null;
  ativa: boolean;
  regra_companheiro: Record<string, string[]>;
  responsavel: Usuario | null;
  /** Assinado e com prazo (12 h): vem novo a cada leitura da obra. */
  logo_url: string | null;
  /** Cor de identidade do empreendimento (#rrggbb), ou null = petróleo. */
  cor: string | null;
  papel: PapelObra | null;
  permissoes: string[];
}

export interface Catalogo {
  id: number;
  codigo: string;
  nome: string;
  ordem: number;
  ativa: boolean;
}

export interface Arquivo {
  id: number;
  nome_original: string;
  tipo: TipoArquivo;
  status: "pendente" | "disponivel" | "erro";
  tamanho: number;
  sha256: string | null;
  content_type: string;
  enviado_em: string;
  enviado_por: Usuario | null;
}

export interface Revisao {
  id: number;
  numero: string;
  ordem: number;
  status: StatusRevisao;
  descricao: string | null;
  descricao_ia: string | null;
  criada_em: string;
  publicada_em: string | null;
  obsoleta_em: string | null;
  criada_por: Usuario | null;
  publicada_por: Usuario | null;
  arquivos: Arquivo[];
}

export interface RevisaoResumo {
  id: number;
  numero: string;
  status: StatusRevisao;
  publicada_em: string | null;
  criada_em: string;
}

export interface Anexo {
  id: number;
  nome_original: string;
  content_type: string;
  tamanho: number;
}

/** Pedido de alteração num projeto liberado. Fecha quando a revisão nova é liberada. */
/** Aviso no sininho: pedido de revisão ou revisão liberada para obra. */
export interface Notificacao {
  id: number;
  tipo:
    | "solicitacao_revisao"
    | "revisao_autorizada"
    | "solicitacao_recusada"
    | "revisao_enviada"
    | "revisao_liberada";
  titulo: string;
  texto: string;
  criada_em: string;
  lida: boolean;
  documento_id: number | null;
  obra_codigo: string;
}

export interface Solicitacao {
  id: number;
  descricao: string;
  /** aberta = esperando o coordenador; autorizada = libera a revisão nova. */
  status: "aberta" | "autorizada" | "atendida" | "recusada";
  criada_em: string;
  criada_por: Usuario | null;
  revisao_numero: string | null;
  atendida_em: string | null;
  atendida_por_numero: string | null;
  decidida_em: string | null;
  decidida_por: Usuario | null;
  motivo_recusa: string | null;
  anexos: Anexo[];
}

/** Pedido na lista de todas as obras (administrador): leva junto onde está. */
export interface SolicitacaoGeral extends Solicitacao {
  obra_id: number;
  obra_codigo: string;
  obra_nome: string;
  documento_id: number;
  documento_codigo: string;
  documento_titulo: string | null;
}

export interface Documento {
  id: number;
  codigo: string;
  titulo: string | null;
  obra_id: number;
  disciplina: Catalogo;
  fase: Catalogo;
  criado_em: string;
  total_revisoes: number;
  revisao_atual: RevisaoResumo | null;
  /** Pedidos esperando o coordenador, e revisões já autorizadas — as marcas
   *  ao lado do status. */
  solicitacoes_abertas: number;
  solicitacoes_autorizadas: number;
}

export interface DocumentoDetalhe extends Documento {
  revisoes: Revisao[];
  solicitacoes: Solicitacao[];
}

export interface Pagina<T> {
  itens: T[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export interface Padrao {
  id: number;
  obra_id: number | null;
  nome: string;
  template: string;
  tokens: Record<string, Record<string, unknown>>;
  extensoes: string[];
  exemplo: string | null;
  ativo: boolean;
}

export interface NomeAnalisado {
  nome_arquivo: string;
  valido: boolean;
  erros: string[];
  codigo_documento: string | null;
  disciplina: string | null;
  fase: string | null;
  revisao: string | null;
  titulo: string | null;
  tipo: TipoArquivo | null;
  documento_existe: boolean;
  /** Título que o documento já tem, para quem envia a revisão seguinte conferir. */
  documento_titulo: string | null;
  /** O envio vai exigir título (documento novo, ou antigo que ficou sem). */
  precisa_titulo: boolean;
  revisao_existe: boolean;
  /** O envio vai exigir "o que mudou": é o primeiro arquivo da revisão. */
  precisa_descricao: boolean;
  revisao_status: StatusRevisao | null;
}

export interface Verificacao {
  pode_publicar: boolean;
  tem_permissao: boolean;
  impedimentos: string[];
  tipos_presentes: string[];
  regra_companheiro: Record<string, string[]>;
}

export interface Membro {
  id: number;
  usuario_id: number;
  papel: PapelObra;
  usuario: Usuario;
}

export interface Evento {
  id: number;
  acao: string;
  entidade: string;
  entidade_id: number | null;
  detalhes: Record<string, unknown>;
  ip: string | null;
  criado_em: string;
  usuario: Usuario | null;
}

/* ------------------------------------------------------------- utilitários */

export const ROTULO_STATUS: Record<StatusRevisao, string> = {
  em_revisao: "Em revisão",
  liberado_para_obra: "Liberado",
  obsoleto: "Obsoleto",
  cancelado: "Cancelado",
};

export const ROTULO_PAPEL: Record<PapelObra, string> = {
  coordenador: "Coordenador",
  projetista: "Projetista",
  obra: "Obra",
};

export function formatarTamanho(bytes: number): string {
  if (!bytes) return "—";
  const unidades = ["B", "KB", "MB", "GB"];
  let valor = bytes;
  let i = 0;
  while (valor >= 1024 && i < unidades.length - 1) {
    valor /= 1024;
    i++;
  }
  return `${valor.toFixed(valor >= 10 || i === 0 ? 0 : 1)} ${unidades[i]}`;
}

export function formatarData(iso: string | null, comHora = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const data = d.toLocaleDateString("pt-BR");
  return comHora ? `${data} ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}` : data;
}
