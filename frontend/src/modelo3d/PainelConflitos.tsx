/** Conflitos entre disciplinas no visualizador 3D (TREELE, 22/10/2026). A
 *  pessoa escolhe um conjunto — pronto ou montado pelo coordenador: quais
 *  disciplinas e categorias formam o grupo A e o grupo B, o tipo de teste e a
 *  tolerância — e o navegador testa os modelos abertos na cena.
 *
 *  Cada detecção é registrada no servidor (api/conflitos.py), que mantém a
 *  situação de cada conflito entre as rodadas e as revisões: novo, ativo,
 *  aprovado (aceito pelo coordenador, com justificativa) e resolvido. Os
 *  conjuntos são da obra, compartilhados pela equipe. */

import { useEffect, useMemo, useRef, useState } from "react";
import { api, ErroApi, formatarData } from "../api";
import {
  conjuntosProntos,
  nomeCategoria,
  type ConjuntoConflito,
  type Conflito,
  type Fase,
  type GrupoConflito,
} from "./conflitos";
import type { Motor } from "./motor";

export interface ModeloConflito {
  modelId: string;
  disciplina: string;
  documento: string;
  documentoId: number;
  revisao: string;
}

/** O que a tela leva para a nova vista de um conflito. */
export interface PedidoVistaConflito {
  titulo: string;
  descricao: string;
  documentoId: number | null;
  /** A vista criada fica ligada a este conflito. */
  conflitoId?: number;
}

type Situacao = "novo" | "ativo" | "aprovado" | "resolvido";

interface ConjuntoServidor {
  id: number;
  nome: string;
  pronto: string | null;
  config: Omit<ConjuntoConflito, "id" | "nome">;
  contagem: Partial<Record<Situacao, number>>;
  ultima_rodada: {
    feita_em: string;
    feita_por: string | null;
    encontrados: number;
    novos: number;
    reabertos: number;
    resolvidos: number;
  } | null;
}

interface ConflitoServidor {
  id: number;
  status: Situacao;
  tipo: "interferencia" | "folga";
  documento_a_id: number | null;
  documento_b_id: number | null;
  documento_a: string | null;
  documento_b: string | null;
  disciplina_a: string | null;
  disciplina_b: string | null;
  revisao_a: string;
  revisao_b: string;
  categoria_a: string;
  categoria_b: string;
  nome_a: string | null;
  nome_b: string | null;
  guids_a: string[];
  guid_b: string;
  centro: number[];
  caixa: { min?: number[]; max?: number[] };
  medida: number;
  visto_em: string;
  resolvido_em: string | null;
  vista_id: number | null;
  justificativa: string | null;
  atualizado_por: string | null;
}

interface ResumoObra {
  abertos: number;
  pares: { disciplina_a: string; disciplina_b: string; novo: number; ativo: number }[];
}

/** Uma opção da lista: um conjunto da obra ou um pronto ainda não usado. */
interface Opcao {
  chave: string;
  conjunto: ConjuntoConflito;
  servidor: ConjuntoServidor | null;
  pronto: string | null;
}

const ROTULO_FASE: Record<Fase, string> = {
  elementos: "Separando os elementos dos grupos…",
  triagem: "Triando os pares que se tocam…",
  geometria: "Lendo a geometria dos pares…",
  teste: "Testando as malhas…",
  nomes: "Organizando os resultados…",
};

const ROTULO_SITUACAO: Record<Situacao, string> = {
  novo: "Novo",
  ativo: "Ativo",
  aprovado: "Aprovado",
  resolvido: "Resolvido",
};

type Filtro = "abertos" | "aprovado" | "resolvido" | "todos";

const FILTROS: [Filtro, string][] = [
  ["abertos", "Abertos"],
  ["aprovado", "Aprovados"],
  ["resolvido", "Resolvidos"],
  ["todos", "Todos"],
];

function passa(c: ConflitoServidor, filtro: Filtro) {
  if (filtro === "todos") return true;
  if (filtro === "abertos") return c.status === "novo" || c.status === "ativo";
  return c.status === filtro;
}

// Os conjuntos do protótipo ficavam no navegador (22/10/2026): o coordenador
// que os montou os leva para a obra na primeira vez que abre o painel.
function chaveAntiga(obraId: number) {
  return `treele.conflitos.${obraId}`;
}

function medidaTexto(m: number): string {
  if (m < 0.01) return `${Math.round(m * 1000)} mm`;
  return `${(m * 100).toFixed(m < 0.1 ? 1 : 0).replace(".", ",")} cm`;
}

function nomeCurto(nome: string | null): string {
  if (!nome) return "sem nome";
  // Revit: "Família:Tipo:123456" — o número do fim não diz nada a ninguém.
  return nome.replace(/:\d+$/, "");
}

function mensagem(e: unknown, padrao: string) {
  return e instanceof ErroApi || e instanceof Error ? e.message : padrao;
}

export default function PainelConflitos({
  motor,
  obraId,
  modelos,
  podeGerenciar,
  podeAprovar,
  versao,
  aoNovaVista,
}: {
  motor: Motor;
  obraId: number;
  modelos: ModeloConflito[];
  /** Monta, muda e apaga conjuntos (coordenador). */
  podeGerenciar: boolean;
  /** Aprova e reabre conflitos (coordenador). */
  podeAprovar: boolean;
  /** Muda quando algo fora do painel mexeu num conflito (a vista criada). */
  versao: number;
  aoNovaVista: (pedido: PedidoVistaConflito) => void;
}) {
  const disciplinas = useMemo(() => [...new Set(modelos.map((m) => m.disciplina))].sort(), [modelos]);
  const prontos = useMemo(() => conjuntosProntos(disciplinas), [disciplinas]);
  const [daObra, setDaObra] = useState<ConjuntoServidor[] | null>(null);
  const [escolhido, setEscolhido] = useState<string>("");
  const [editando, setEditando] = useState<{ conjunto: ConjuntoConflito; servidorId: number | null } | null>(null);
  const [andamento, setAndamento] = useState<{ fase: Fase; valor: number } | null>(null);
  const [lista, setLista] = useState<ConflitoServidor[] | null>(null);
  const [ultimaVez, setUltimaVez] = useState<{ segundos: number; encontrados: number } | null>(null);
  const [filtro, setFiltro] = useState<Filtro>("abertos");
  const [resumo, setResumo] = useState<ResumoObra | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ativo, setAtivo] = useState<number | null>(null);
  const [aprovando, setAprovando] = useState<{ id: number; texto: string } | null>(null);
  const rodando = useRef(false);
  // Os conflitos achados nesta sessão, com as peças já localizadas na cena.
  const locais = useRef<Map<number, Conflito>>(new Map());

  // Os prontos que a obra já usou viram conjuntos dela; os outros aparecem
  // como prontos e nascem na primeira rodada. A configuração do pronto é
  // sempre a de agora (as disciplinas da cena).
  const opcoes: Opcao[] = useMemo(() => {
    const doServidor = daObra ?? [];
    const proprios = doServidor
      .filter((s) => !s.pronto)
      .map<Opcao>((s) => ({ chave: `s${s.id}`, conjunto: { ...s.config, id: `s${s.id}`, nome: s.nome }, servidor: s, pronto: null }));
    const doSistema = prontos.map<Opcao>((p) => {
      const pronto = p.id.replace(/^pronto-/, "");
      const s = doServidor.find((x) => x.pronto === pronto) ?? null;
      return { chave: p.id, conjunto: p, servidor: s, pronto };
    });
    return [...proprios, ...doSistema];
  }, [daObra, prontos]);
  const opcao = opcoes.find((o) => o.chave === escolhido) ?? opcoes[0];

  async function carregarConjuntos() {
    try {
      setDaObra(await api.get<ConjuntoServidor[]>(`/obras/${obraId}/conjuntos-conflito`));
    } catch (e) {
      setErro(mensagem(e, "Não foi possível carregar os conjuntos da obra."));
      setDaObra([]);
    }
  }

  async function carregarResumo() {
    try {
      setResumo(await api.get<ResumoObra>(`/obras/${obraId}/conflitos/resumo`));
    } catch {
      setResumo(null);
    }
  }

  useEffect(() => {
    void (async () => {
      if (podeGerenciar) await levarConjuntosAntigos();
      await carregarConjuntos();
      await carregarResumo();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [obraId]);

  async function levarConjuntosAntigos() {
    let antigos: ConjuntoConflito[] = [];
    try {
      antigos = JSON.parse(localStorage.getItem(chaveAntiga(obraId)) ?? "[]") as ConjuntoConflito[];
    } catch {
      return;
    }
    if (!antigos.length) return;
    try {
      for (const { id: _id, nome, ...config } of antigos) {
        await api.post(`/obras/${obraId}/conjuntos-conflito`, { nome, config });
      }
      localStorage.removeItem(chaveAntiga(obraId));
    } catch {
      // Fica para a próxima abertura.
    }
  }

  // A lista guardada do conjunto escolhido, sem precisar detectar de novo.
  async function carregarLista(o: Opcao | undefined) {
    if (!o?.servidor) {
      setLista(null);
      return;
    }
    try {
      setLista(await api.get<ConflitoServidor[]>(`/conjuntos-conflito/${o.servidor.id}/conflitos`));
    } catch (e) {
      setErro(mensagem(e, "Não foi possível carregar os conflitos."));
    }
  }

  // Trocar de conjunto recarrega a lista; o pronto ganhando número no
  // servidor (na primeira rodada) não — a rodada acabou de trazê-la.
  const chaveCarregada = useRef<string | null>(null);
  useEffect(() => {
    if (!opcao || (opcao.chave === chaveCarregada.current && lista)) return;
    chaveCarregada.current = opcao.chave;
    setAtivo(null);
    setUltimaVez(null);
    void carregarLista(opcao);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opcao?.chave, opcao?.servidor?.id]);

  useEffect(() => {
    if (versao) void carregarLista(opcao);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versao]);

  // Categorias de cada disciplina na cena, com a contagem.
  const [categorias, setCategorias] = useState<Record<string, Record<string, number>>>({});
  useEffect(() => {
    let vivo = true;
    (async () => {
      const porDisciplina: Record<string, Record<string, number>> = {};
      for (const m of modelos) {
        const contagem = await motor.categorias(m.modelId);
        const alvo = (porDisciplina[m.disciplina] ??= {});
        for (const [c, n] of Object.entries(contagem)) alvo[c] = (alvo[c] ?? 0) + n;
      }
      if (vivo) setCategorias(porDisciplina);
    })();
    return () => {
      vivo = false;
    };
  }, [motor, modelos]);

  /** O conjunto no servidor: o pronto nasce agora, se for a primeira vez. */
  async function noServidor(o: Opcao): Promise<ConjuntoServidor> {
    if (o.servidor) return o.servidor;
    const { id: _id, nome, ...config } = o.conjunto;
    return await api.post<ConjuntoServidor>(`/obras/${obraId}/conjuntos-conflito`, {
      nome,
      config,
      pronto: o.pronto,
    });
  }

  async function rodar(o: Opcao) {
    // Uma detecção por vez: duas ao mesmo tempo disputam o mesmo worker.
    if (rodando.current) return;
    rodando.current = true;
    setAndamento({ fase: "elementos", valor: 0 });
    setErro(null);
    setAtivo(null);
    await motor.focarConflito(null);
    const inicio = performance.now();
    try {
      const servidor = await noServidor(o);
      // Sem GlobalId (peça sem identificação no IFC) não há como reconhecer
      // o conflito depois: fica de fora.
      const achados = (
        await motor.detectarConflitos(
          modelos.map((m) => ({ modelId: m.modelId, disciplina: m.disciplina })),
          o.conjunto,
          (fase, valor) => setAndamento({ fase, valor }),
        )
      ).filter((c) => c.a.guids.length && c.b.guids.length);
      const r = await api.post<{ conjunto: ConjuntoServidor; ids: number[]; conflitos: ConflitoServidor[] }>(
        `/conjuntos-conflito/${servidor.id}/rodadas`,
        {
          arquivos: modelos.map((m) => Number(m.modelId)),
          achados: achados.map((c) => ({
            arquivo_a_id: Number(c.a.modelId),
            arquivo_b_id: Number(c.b.modelId),
            guids_a: c.a.guids.slice(0, 200),
            guid_b: c.b.guids[0],
            categoria_a: c.a.categoria,
            categoria_b: c.b.categoria,
            nome_a: c.a.nome?.slice(0, 300) ?? null,
            nome_b: c.b.nome?.slice(0, 300) ?? null,
            tipo: c.tipo,
            centro: c.centro,
            caixa_min: c.caixa.min,
            caixa_max: c.caixa.max,
            medida: c.medida,
          })),
        },
      );
      locais.current = new Map(r.ids.map((id, i) => [id, achados[i]]));
      setUltimaVez({ segundos: (performance.now() - inicio) / 1000, encontrados: achados.length });
      setDaObra((atual) => [...(atual ?? []).filter((s) => s.id !== r.conjunto.id), r.conjunto]);
      setEscolhido(r.conjunto.pronto ? o.chave : `s${r.conjunto.id}`);
      setLista(r.conflitos);
      setFiltro("abertos");
      void carregarResumo();
    } catch (e) {
      setErro(mensagem(e, "A detecção falhou."));
    } finally {
      rodando.current = false;
      setAndamento(null);
    }
  }

  /** O conflito na cena: as peças desta rodada, ou as achadas pelos GlobalIds. */
  async function naCena(c: ConflitoServidor): Promise<Conflito> {
    const local = locais.current.get(c.id);
    if (local) return local;
    const lado = async (documentoId: number | null, guids: string[], categoria: string, nome: string | null) => {
      const m = modelos.find((x) => x.documentoId === documentoId);
      return {
        modelId: m?.modelId ?? "",
        localIds: m ? await motor.idsDosGuids(m.modelId, guids) : [],
        guids,
        nome,
        categoria,
      };
    };
    const centro = (c.centro.length === 3 ? c.centro : [0, 0, 0]) as [number, number, number];
    return {
      id: c.id,
      tipo: c.tipo,
      a: await lado(c.documento_a_id, c.guids_a, c.categoria_a, c.nome_a),
      b: await lado(c.documento_b_id, [c.guid_b], c.categoria_b, c.nome_b),
      centro,
      caixa: {
        min: (c.caixa.min ?? centro) as [number, number, number],
        max: (c.caixa.max ?? centro) as [number, number, number],
      },
      medida: c.medida,
    };
  }

  async function focar(c: ConflitoServidor) {
    setAtivo(c.id);
    setAprovando(null);
    await motor.focarConflito(await naCena(c));
  }

  async function mudar(c: ConflitoServidor, corpo: { status: "aprovado" | "ativo"; justificativa?: string }) {
    try {
      const novo = await api.patch<ConflitoServidor>(`/conflitos/${c.id}`, corpo);
      setLista((l) => l?.map((x) => (x.id === novo.id ? novo : x)) ?? l);
      setAprovando(null);
      void carregarResumo();
    } catch (e) {
      setErro(mensagem(e, "Não foi possível mudar o conflito."));
    }
  }

  async function guardar(c: ConjuntoConflito, servidorId: number | null): Promise<Opcao | null> {
    const { id: _id, nome, ...config } = c;
    try {
      const s = servidorId
        ? await api.patch<ConjuntoServidor>(`/conjuntos-conflito/${servidorId}`, { nome, config })
        : await api.post<ConjuntoServidor>(`/obras/${obraId}/conjuntos-conflito`, { nome, config });
      setDaObra((atual) => [...(atual ?? []).filter((x) => x.id !== s.id), s]);
      setEscolhido(`s${s.id}`);
      return { chave: `s${s.id}`, conjunto: { ...s.config, id: `s${s.id}`, nome: s.nome }, servidor: s, pronto: null };
    } catch (e) {
      setErro(mensagem(e, "Não foi possível guardar o conjunto."));
      return null;
    }
  }

  async function apagar(o: Opcao) {
    if (!o.servidor) return;
    const total = Object.values(o.servidor.contagem).reduce((s, n) => s + (n ?? 0), 0);
    if (!window.confirm(`Apagar o conjunto "${o.servidor.nome}" e o histórico de ${total} conflito(s)?`)) return;
    try {
      await api.delete(`/conjuntos-conflito/${o.servidor.id}`);
      setDaObra((atual) => (atual ?? []).filter((x) => x.id !== o.servidor!.id));
      setEscolhido("");
      void carregarResumo();
    } catch (e) {
      setErro(mensagem(e, "Não foi possível apagar o conjunto."));
    }
  }

  function pedirVista(c: ConflitoServidor) {
    const cA = nomeCategoria(c.categoria_a);
    const cB = nomeCategoria(c.categoria_b);
    const medida =
      c.tipo === "interferencia" ? `entra cerca de ${medidaTexto(c.medida)}` : `fica a ${medidaTexto(c.medida)}`;
    const nomeB = nomeCurto(c.nome_b);
    const cota = (c.centro[1] ?? 0).toFixed(2).replace(".", ",");
    aoNovaVista({
      titulo: `Conflito: ${cA} × ${cB}${nomeB.length <= 16 ? ` ${nomeB}` : ""}${
        c.disciplina_a && c.disciplina_b ? ` (${c.disciplina_a} × ${c.disciplina_b})` : ""
      }`,
      descricao:
        `${cA} "${nomeCurto(c.nome_a)}"${c.documento_a ? ` (${c.documento_a} R${c.revisao_a})` : ""} ${medida} ` +
        `${c.tipo === "interferencia" ? "em" : "de"} ${cB.toLowerCase()} "${nomeB}"` +
        `${c.documento_b ? ` (${c.documento_b} R${c.revisao_b})` : ""}, na cota ${cota} m. ` +
        "Ajustar o traçado ou prever a passagem com o projetista de estrutura.",
      documentoId: c.documento_a_id,
      conflitoId: c.id,
    });
  }

  const ordem: Record<Situacao, number> = { novo: 0, ativo: 1, aprovado: 2, resolvido: 3 };
  const visiveis = (lista ?? [])
    .filter((c) => passa(c, filtro))
    .sort((p, q) => ordem[p.status] - ordem[q.status] || (p.centro[1] ?? 0) - (q.centro[1] ?? 0));
  const contagem = (f: Filtro) => (lista ?? []).filter((c) => passa(c, f)).length;
  const rodada = opcao?.servidor?.ultima_rodada;

  return (
    <div className="painel-conflitos">
      <span className="rotulo">Conflitos entre disciplinas</span>
      {resumo && resumo.abertos > 0 && (
        <p className="silencioso" style={{ fontSize: 12, margin: 0 }}>
          <b>{resumo.abertos} abertos na obra</b>
          {" — "}
          {resumo.pares
            .filter((p) => p.novo + p.ativo > 0)
            .slice(0, 5)
            .map((p) => `${p.disciplina_a} × ${p.disciplina_b} ${p.novo + p.ativo}`)
            .join(" · ")}
        </p>
      )}
      {disciplinas.length < 1 ? (
        <p className="silencioso" style={{ fontSize: 12.5 }}>
          Abra os modelos das disciplinas na cena para testar.
        </p>
      ) : (
        <>
          <label className="campo" style={{ display: "block" }}>
            <select
              value={opcao?.chave ?? ""}
              onChange={(e) => setEscolhido(e.target.value)}
              disabled={!!andamento || daObra === null}
            >
              {opcoes.some((o) => !o.pronto) && (
                <optgroup label="Conjuntos da obra">
                  {opcoes
                    .filter((o) => !o.pronto)
                    .map((o) => (
                      <option key={o.chave} value={o.chave}>
                        {o.conjunto.nome}
                      </option>
                    ))}
                </optgroup>
              )}
              <optgroup label="Prontos">
                {opcoes
                  .filter((o) => o.pronto)
                  .map((o) => (
                    <option key={o.chave} value={o.chave}>
                      {o.conjunto.nome}
                    </option>
                  ))}
              </optgroup>
            </select>
          </label>
          {opcao && <ResumoConjunto conjunto={opcao.conjunto} />}
          {rodada && (
            <p className="silencioso" style={{ fontSize: 11.5, margin: 0 }}>
              Última detecção: {formatarData(rodada.feita_em)}
              {rodada.feita_por && `, por ${rodada.feita_por}`} — {rodada.encontrados} encontrados
              {rodada.novos > 0 && `, ${rodada.novos} novos`}
              {rodada.resolvidos > 0 && `, ${rodada.resolvidos} resolvidos`}
              {rodada.reabertos > 0 && `, ${rodada.reabertos} reabertos`}.
            </p>
          )}
          <div className="linha" style={{ gap: 6, flexWrap: "wrap" }}>
            <button className="botao pequeno" disabled={!opcao || !!andamento} onClick={() => opcao && rodar(opcao)}>
              Detectar
            </button>
            {podeGerenciar && (
              <>
                <button
                  className="botao secundario pequeno"
                  disabled={!opcao || !!andamento}
                  onClick={() =>
                    opcao &&
                    setEditando(
                      opcao.pronto
                        ? { conjunto: { ...opcao.conjunto, nome: `${opcao.conjunto.nome} (cópia)` }, servidorId: null }
                        : { conjunto: opcao.conjunto, servidorId: opcao.servidor?.id ?? null },
                    )
                  }
                  title={opcao?.pronto ? "O pronto não muda: a configuração vira um conjunto da obra" : undefined}
                >
                  Configurar…
                </button>
                <button
                  className="botao secundario pequeno"
                  disabled={!!andamento}
                  onClick={() =>
                    setEditando({ conjunto: { ...prontos[0], id: "novo", nome: "Novo conjunto" }, servidorId: null })
                  }
                >
                  Novo
                </button>
                {opcao && !opcao.pronto && (
                  <button className="link-pequeno" disabled={!!andamento} onClick={() => apagar(opcao)}>
                    Apagar
                  </button>
                )}
              </>
            )}
          </div>
        </>
      )}

      {andamento && (
        <div className="andamento-modelo">
          <span>{ROTULO_FASE[andamento.fase]}</span>
          <div className="progresso-lote">
            <span style={{ width: `${Math.round(andamento.valor * 100)}%` }} />
          </div>
        </div>
      )}
      {erro && <p className="erro-modelo">{erro}</p>}

      {lista && (
        <div>
          {ultimaVez && (
            <p style={{ margin: "4px 0", fontSize: 13 }}>
              <strong>
                {ultimaVez.encontrados === 0
                  ? "Nenhum conflito"
                  : `${ultimaVez.encontrados} conflito${ultimaVez.encontrados > 1 ? "s" : ""}`}
              </strong>{" "}
              <span className="silencioso">nesta detecção · {ultimaVez.segundos.toFixed(1).replace(".", ",")} s</span>
            </p>
          )}
          <div className="filtros-conflito" role="tablist">
            {FILTROS.map(([f, rotulo]) => (
              <button
                key={f}
                role="tab"
                aria-selected={filtro === f}
                className={filtro === f ? "ativo" : undefined}
                onClick={() => setFiltro(f)}
              >
                {rotulo} <span>{contagem(f)}</span>
              </button>
            ))}
          </div>
          {visiveis.length === 0 && (
            <p className="silencioso" style={{ fontSize: 12.5, margin: "6px 0 0" }}>
              {filtro === "abertos" ? "Nenhum conflito aberto neste conjunto." : "Nada aqui."}
            </p>
          )}
          <ol className="lista-conflitos">
            {visiveis.slice(0, 300).map((c, i) => (
              <li key={c.id} className={c.id === ativo ? "atual" : undefined}>
                <button className="conflito-item" onClick={() => focar(c)}>
                  <span className="conflito-numero">{i + 1}</span>
                  <span style={{ minWidth: 0 }}>
                    <span className="conflito-lado">
                      <b>{nomeCategoria(c.categoria_a)}</b>
                      {c.guids_a.length > 1 && ` (${c.guids_a.length} peças)`} · {nomeCurto(c.nome_a)}
                    </span>
                    <span className="conflito-lado">
                      × <b>{nomeCategoria(c.categoria_b)}</b> · {nomeCurto(c.nome_b)}
                    </span>
                    <span className="silencioso conflito-meta">
                      <span className={`situacao-conflito ${c.status}`}>{ROTULO_SITUACAO[c.status]}</span>{" "}
                      {c.disciplina_a} × {c.disciplina_b} ·{" "}
                      {c.tipo === "interferencia" ? `entra ~${medidaTexto(c.medida)}` : `a ${medidaTexto(c.medida)}`} ·
                      cota {(c.centro[1] ?? 0).toFixed(2).replace(".", ",")} m
                      {c.vista_id && " · com vista"}
                    </span>
                  </span>
                </button>
                {c.id === ativo && (
                  <div className="acoes-conflito">
                    {c.justificativa && (
                      <p className="silencioso" style={{ fontSize: 12, margin: 0 }}>
                        Aprovado{c.atualizado_por ? ` por ${c.atualizado_por}` : ""}: {c.justificativa}
                      </p>
                    )}
                    {c.status === "resolvido" && c.resolvido_em && (
                      <p className="silencioso" style={{ fontSize: 12, margin: 0 }}>
                        Não apareceu na detecção de {formatarData(c.resolvido_em)}.
                      </p>
                    )}
                    <div className="linha" style={{ gap: 6, flexWrap: "wrap" }}>
                      <button className="botao pequeno" onClick={() => pedirVista(c)}>
                        Nova vista
                      </button>
                      {c.vista_id && (
                        <a className="botao secundario pequeno" href={`/modelos?vista=${c.vista_id}`}>
                          Abrir a vista
                        </a>
                      )}
                      {podeAprovar && (c.status === "novo" || c.status === "ativo") && (
                        <button
                          className="botao secundario pequeno"
                          onClick={() => setAprovando({ id: c.id, texto: "" })}
                          title="Conflito aceito, que não precisa de correção (ex.: furo previsto na viga)"
                        >
                          Aprovar…
                        </button>
                      )}
                      {podeAprovar && (c.status === "aprovado" || c.status === "resolvido") && (
                        <button className="botao secundario pequeno" onClick={() => mudar(c, { status: "ativo" })}>
                          Reabrir
                        </button>
                      )}
                    </div>
                    {aprovando?.id === c.id && (
                      <form
                        className="aprovar-conflito"
                        onSubmit={(e) => {
                          e.preventDefault();
                          void mudar(c, { status: "aprovado", justificativa: aprovando.texto.trim() });
                        }}
                      >
                        <textarea
                          value={aprovando.texto}
                          onChange={(e) => setAprovando({ id: c.id, texto: e.target.value })}
                          placeholder="Por que é aceito? Ex.: furo previsto na viga V12 pelo calculista."
                          maxLength={2000}
                          rows={2}
                        />
                        <div className="linha" style={{ gap: 6 }}>
                          <button className="botao pequeno" disabled={aprovando.texto.trim().length < 5}>
                            Aprovar
                          </button>
                          <button type="button" className="link-pequeno" onClick={() => setAprovando(null)}>
                            Cancelar
                          </button>
                        </div>
                      </form>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ol>
          {visiveis.length > 300 && (
            <p className="silencioso" style={{ fontSize: 12 }}>
              Mostrando 300 de {visiveis.length}. Afine o conjunto (menos categorias, mais tolerância).
            </p>
          )}
        </div>
      )}

      {editando && (
        <EditorConjunto
          inicial={editando.conjunto}
          disciplinas={disciplinas}
          categorias={categorias}
          aoFechar={() => setEditando(null)}
          aoGuardar={async (c, detectarJa) => {
            const salvo = await guardar(c, editando.servidorId);
            if (!salvo) return;
            setEditando(null);
            if (detectarJa) void rodar(salvo);
          }}
        />
      )}
    </div>
  );
}

function ResumoConjunto({ conjunto }: { conjunto: ConjuntoConflito }) {
  const grupo = (g: GrupoConflito) => {
    const discs = g.disciplinas.join(", ") || "nenhuma disciplina";
    if (g.categorias.length) return `${discs} (${g.categorias.map(nomeCategoria).join(", ")})`;
    const fora = [...new Set((g.excluir ?? []).map(nomeCategoria))];
    return `${discs} (tudo${fora.length ? `, menos ${fora.slice(0, 4).join(", ")}${fora.length > 4 ? "…" : ""}` : ""})`;
  };
  return (
    <p className="silencioso" style={{ fontSize: 12, margin: 0 }}>
      <b>A:</b> {grupo(conjunto.a)}
      <br />
      <b>B:</b> {grupo(conjunto.b)}
      <br />
      {conjunto.modo === "interferencia"
        ? `Interferência, tolerância ${medidaTexto(conjunto.tolerancia)}`
        : `Folga mínima de ${medidaTexto(conjunto.folga)}`}
      {conjunto.ignorarMesmoModelo && " · sem pares do mesmo modelo"}
    </p>
  );
}

/** A janela que monta o conjunto: grupo A, grupo B, tipo e tolerância. */
function EditorConjunto({
  inicial,
  disciplinas,
  categorias,
  aoFechar,
  aoGuardar,
}: {
  inicial: ConjuntoConflito;
  disciplinas: string[];
  categorias: Record<string, Record<string, number>>;
  aoFechar: () => void;
  aoGuardar: (c: ConjuntoConflito, detectarJa: boolean) => void | Promise<void>;
}) {
  const [c, setC] = useState<ConjuntoConflito>(inicial);
  const [erro, setErro] = useState<string | null>(null);

  function concluir(detectarJa: boolean) {
    if (!c.nome.trim()) return setErro("Dê um nome ao conjunto.");
    if (!c.a.disciplinas.length || !c.b.disciplinas.length) return setErro("Escolha ao menos uma disciplina em cada grupo.");
    aoGuardar({ ...c, nome: c.nome.trim() }, detectarJa);
  }

  return (
    <div className="painel-vista-fundo">
      <div className="painel-vista" role="dialog" aria-label="Conjunto de conflitos">
        <div className="linha">
          <strong>Conjunto de conflitos</strong>
          <div className="espaco" />
          <button className="assistente-fechar" onClick={aoFechar} aria-label="Fechar">
            ×
          </button>
        </div>
        <label className="campo" style={{ display: "block", marginTop: 8 }}>
          <span className="rotulo">Nome</span>
          <input value={c.nome} maxLength={80} onChange={(e) => setC({ ...c, nome: e.target.value })} />
        </label>
        <div className="grupos-conflito">
          <EditorGrupo
            titulo="Grupo A"
            dica="O que costuma ser desviado (ex.: tubulações)."
            grupo={c.a}
            disciplinas={disciplinas}
            categorias={categorias}
            aoMudar={(a) => setC({ ...c, a })}
          />
          <EditorGrupo
            titulo="Grupo B"
            dica="Contra o que A é testado. Deixe as lajes de fora para não marcar os furos de laje."
            grupo={c.b}
            disciplinas={disciplinas}
            categorias={categorias}
            aoMudar={(b) => setC({ ...c, b })}
          />
        </div>
        <div className="linha" style={{ gap: 16, flexWrap: "wrap", marginTop: 10 }}>
          <label className="opcao-aviso" style={{ margin: 0 }}>
            <input
              type="radio"
              checked={c.modo === "interferencia"}
              onChange={() => setC({ ...c, modo: "interferencia" })}
            />
            Interferência — uma peça entra na outra mais que
            <input
              type="number"
              min={0}
              max={50}
              step={0.5}
              className="numero-conflito"
              value={Math.round(c.tolerancia * 1000) / 10}
              onChange={(e) => setC({ ...c, tolerancia: Math.max(0, Number(e.target.value) || 0) / 100 })}
            />
            cm
          </label>
          <label className="opcao-aviso" style={{ margin: 0 }}>
            <input type="radio" checked={c.modo === "folga"} onChange={() => setC({ ...c, modo: "folga" })} />
            Folga — ficam a menos de
            <input
              type="number"
              min={0.5}
              max={100}
              step={0.5}
              className="numero-conflito"
              value={Math.round(c.folga * 1000) / 10}
              onChange={(e) => setC({ ...c, folga: Math.max(0.005, (Number(e.target.value) || 0) / 100) })}
            />
            cm (inclui as interferências)
          </label>
        </div>
        <label className="opcao-aviso" style={{ marginTop: 8 }}>
          <input
            type="checkbox"
            checked={c.ignorarMesmoModelo}
            onChange={(e) => setC({ ...c, ignorarMesmoModelo: e.target.checked })}
          />
          Ignorar pares dentro do mesmo modelo
          <span className="silencioso">— tubo com a própria conexão sempre se toca</span>
        </label>
        {erro && <p className="erro-modelo">{erro}</p>}
        <div className="linha" style={{ gap: 8, marginTop: 12 }}>
          <button className="botao" onClick={() => concluir(true)}>
            Guardar e detectar
          </button>
          <button className="botao secundario pequeno" onClick={() => concluir(false)}>
            Só guardar
          </button>
          <button className="botao secundario pequeno" onClick={aoFechar}>
            Cancelar
          </button>
        </div>
        <p className="silencioso" style={{ fontSize: 12, margin: "8px 0 0" }}>
          O conjunto fica na obra, para toda a equipe, e vale para qualquer revisão dos modelos: ele escolhe por
          disciplina e categoria, não por arquivo.
        </p>
      </div>
    </div>
  );
}

function EditorGrupo({
  titulo,
  dica,
  grupo,
  disciplinas,
  categorias,
  aoMudar,
}: {
  titulo: string;
  dica: string;
  grupo: GrupoConflito;
  disciplinas: string[];
  categorias: Record<string, Record<string, number>>;
  aoMudar: (g: GrupoConflito) => void;
}) {
  // As categorias das disciplinas marcadas, com quantos elementos.
  const disponiveis: Record<string, number> = {};
  for (const d of grupo.disciplinas)
    for (const [cat, n] of Object.entries(categorias[d] ?? {})) disponiveis[cat] = (disponiveis[cat] ?? 0) + n;
  const lista = Object.entries(disponiveis).sort((x, y) => nomeCategoria(x[0]).localeCompare(nomeCategoria(y[0])));
  const todas = grupo.categorias.length === 0;
  const excluir = grupo.excluir ?? [];

  return (
    <fieldset className="grupo-conflito">
      <legend>{titulo}</legend>
      <p className="silencioso" style={{ fontSize: 12, margin: "0 0 6px" }}>
        {dica}
      </p>
      <span className="rotulo">Disciplinas</span>
      <div className="linha" style={{ gap: 10, flexWrap: "wrap", margin: "2px 0 8px" }}>
        {disciplinas.map((d) => (
          <label key={d} className="opcao-aviso" style={{ margin: 0 }}>
            <input
              type="checkbox"
              checked={grupo.disciplinas.includes(d)}
              onChange={(e) =>
                aoMudar({
                  ...grupo,
                  disciplinas: e.target.checked
                    ? [...grupo.disciplinas, d]
                    : grupo.disciplinas.filter((x) => x !== d),
                })
              }
            />
            <span className="mono">{d}</span>
          </label>
        ))}
      </div>
      <span className="rotulo">Categorias</span>
      <label className="opcao-aviso" style={{ margin: "2px 0 4px" }}>
        <input
          type="checkbox"
          checked={todas}
          onChange={(e) =>
            aoMudar({
              ...grupo,
              categorias: e.target.checked ? [] : lista.map(([cat]) => cat).filter((cat) => !excluir.includes(cat)),
            })
          }
        />
        Todas, menos as desmarcadas
      </label>
      <ul className="categorias-conflito">
        {lista.map(([cat, n]) => (
          <li key={cat}>
            <label className="opcao-aviso" style={{ margin: 0 }}>
              <input
                type="checkbox"
                checked={todas ? !excluir.includes(cat) : grupo.categorias.includes(cat)}
                onChange={(e) =>
                  aoMudar(
                    todas
                      ? {
                          ...grupo,
                          excluir: e.target.checked ? excluir.filter((x) => x !== cat) : [...excluir, cat],
                        }
                      : {
                          ...grupo,
                          categorias: e.target.checked
                            ? [...grupo.categorias, cat]
                            : grupo.categorias.filter((x) => x !== cat),
                        },
                  )
                }
              />
              {nomeCategoria(cat)}
              <span className="silencioso mono" style={{ fontSize: 11 }}>
                {" "}
                {cat} · {n}
              </span>
            </label>
          </li>
        ))}
        {grupo.categorias
          .filter((cat) => !(cat in disponiveis))
          .map((cat) => (
            <li key={cat} className="silencioso">
              <label className="opcao-aviso" style={{ margin: 0 }}>
                <input
                  type="checkbox"
                  checked
                  onChange={() => aoMudar({ ...grupo, categorias: grupo.categorias.filter((x) => x !== cat) })}
                />
                {nomeCategoria(cat)} <span className="mono" style={{ fontSize: 11 }}>(não está nos modelos abertos)</span>
              </label>
            </li>
          ))}
      </ul>
    </fieldset>
  );
}
