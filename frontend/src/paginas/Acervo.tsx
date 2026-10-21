import { useCallback, useEffect, useRef, useState } from "react";
import { downloadZip } from "client-zip";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  api,
  ErroApi,
  formatarData,
  lerToken,
  type Documento,
  type Pagina,
  type StatusRevisao,
  type TipoArquivo,
} from "../api";
import Arvore from "../Arvore";
import { MarcaSolicitada } from "../Solicitacoes";
import { Aviso, CapaObra, Carregando, Estado, Vazio } from "../componentes";
import { useSessao } from "../sessao";

const TAMANHOS_PAGINA = [50, 100, 200];
const CHAVE_VISAO = "treele.acervo.visao";

type Visao = "lista" | "arvore";

/** Revisão marcada para baixar ou liberar em lote — guarda o que a tela
 *  mostra dela. */
interface Marcada {
  documento: string;
  numero: string;
  status: StatusRevisao;
}

/** Arquivo que pode entrar no download em lote (POST /revisoes/arquivos-lote). */
interface ArquivoLote {
  id: number;
  nome: string;
  tipo: string;
  tamanho: number | null;
  documento: string;
  revisao: string;
  pasta: string;
  aviso: string | null;
}

interface ListaDownload {
  arquivos: ArquivoLote[];
  recusadas: ItemLote[];
}

interface Progresso {
  feitos: number;
  total: number;
  bytes: number;
}

const ROTULO_TIPO: Record<string, string> = {
  pdf: "PDF",
  dwg: "DWG",
  ifc: "IFC",
  rvt: "RVT",
  outro: "Outros",
};
const ORDEM_TIPO = ["pdf", "dwg", "ifc", "rvt", "outro"];

function tamanhoLegivel(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1).replace(".", ",")} GB`;
  if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

type JanelaComSalvar = Window & {
  showSaveFilePicker?: (opcoes: {
    suggestedName: string;
    types: { description: string; accept: Record<string, string[]> }[];
  }) => Promise<{ createWritable: () => Promise<WritableStream<Uint8Array>> }>;
};

interface ItemLote {
  revisao_id: number;
  documento: string | null;
  revisao: string | null;
  motivos: string[];
}

interface ResultadoLote {
  liberadas: ItemLote[];
  recusadas: ItemLote[];
}

export default function Acervo() {
  const { obraId } = useParams();
  const { obras, disciplinas: todasDisciplinas, fases, usuario } = useSessao();
  // O comercial só enxerga a disciplina COM: oferecer as outras no filtro
  // seria oferecer listas sempre vazias.
  const disciplinas = usuario?.comercial
    ? todasDisciplinas.filter((d) => d.codigo === "COM")
    : todasDisciplinas;
  const obra = obras.find((o) => o.id === Number(obraId));

  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [disciplina, setDisciplina] = useState("");
  const [fase, setFase] = useState("");
  const [status, setStatus] = useState<StatusRevisao | "">("");
  const [tipo, setTipo] = useState<TipoArquivo | "">("");
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(TAMANHOS_PAGINA[0]);
  // Liberação em lote (TREELE, 15/10/2026): a seleção sobrevive à troca de
  // página e de filtro — dá para marcar de várias páginas e liberar de uma vez.
  const podeLiberar = obra?.permissoes.includes("publicar") ?? false;
  const [marcadas, setMarcadas] = useState<Map<number, Marcada>>(new Map());
  const [painelLote, setPainelLote] = useState<"liberar" | "baixar" | null>(null);
  // Download em lote (TREELE, 21/10/2026): marca as linhas, escolhe os
  // formatos e baixa um ZIP com obra/disciplina/arquivo.
  const [listaDownload, setListaDownload] = useState<ListaDownload | null>(null);
  const [tiposMarcados, setTiposMarcados] = useState<Set<string>>(new Set());
  const [baixando, setBaixando] = useState<Progresso | null>(null);
  const [resultadoDownload, setResultadoDownload] = useState<{
    baixados: number;
    falhas: string[];
    cancelado: boolean;
  } | null>(null);
  const cancelarDownload = useRef<AbortController | null>(null);
  const [observacaoLote, setObservacaoLote] = useState("");
  const [avisarLote, setAvisarLote] = useState(true);
  const [liberando, setLiberando] = useState(false);
  const [resultadoLote, setResultadoLote] = useState<ResultadoLote | null>(null);
  // Vindo de um link de pasta (?pasta=ARQ/PE): abre nas pastas, com ela aberta.
  const [parametros] = useSearchParams();
  const pastaPedida = parametros.get("pasta") ?? undefined;
  const [visao, setVisao] = useState<Visao>(() =>
    pastaPedida ? "arvore" : (localStorage.getItem(CHAVE_VISAO) as Visao) || "lista",
  );

  const [dados, setDados] = useState<Pagina<Documento> | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  // Debounce da busca: evita uma consulta por tecla digitada.
  useEffect(() => {
    const t = setTimeout(() => {
      setBuscaAplicada(busca);
      setPagina(1);
    }, 300);
    return () => clearTimeout(t);
  }, [busca]);

  const consultar = useCallback(async () => {
    if (!obraId || visao !== "lista") return;
    setCarregando(true);
    setErro(null);
    const p = new URLSearchParams({ pagina: String(pagina), por_pagina: String(porPagina) });
    if (buscaAplicada.trim()) p.set("busca", buscaAplicada.trim());
    if (disciplina) p.set("disciplina_id", disciplina);
    if (fase) p.set("fase_id", fase);
    if (status) p.set("status_revisao", status);
    if (tipo) p.set("tipo", tipo);

    try {
      setDados(await api.get<Pagina<Documento>>(`/obras/${obraId}/documentos?${p}`));
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível carregar o acervo.");
    } finally {
      setCarregando(false);
    }
  }, [obraId, visao, pagina, porPagina, buscaAplicada, disciplina, fase, status, tipo]);

  function alternar(d: Documento) {
    const rev = d.revisao_atual;
    if (!rev) return;
    setMarcadas((m) => {
      const novo = new Map(m);
      if (novo.has(rev.id)) novo.delete(rev.id);
      else novo.set(rev.id, { documento: d.codigo, numero: rev.numero, status: rev.status });
      return novo;
    });
  }

  function alternarPagina(marcar: boolean) {
    if (!dados) return;
    setMarcadas((m) => {
      const novo = new Map(m);
      for (const d of dados.itens) {
        const rev = d.revisao_atual;
        if (!rev) continue;
        if (marcar) novo.set(rev.id, { documento: d.codigo, numero: rev.numero, status: rev.status });
        else novo.delete(rev.id);
      }
      return novo;
    });
  }

  // Só as marcadas em análise entram na liberação; as outras (já liberadas,
  // obsoletas) servem só para o download.
  const marcadasEmRevisao = [...marcadas.entries()].filter(([, m]) => m.status === "em_revisao");

  async function abrirDownload() {
    setPainelLote("baixar");
    setListaDownload(null);
    setResultadoDownload(null);
    setErro(null);
    try {
      const r = await api.post<ListaDownload>("/revisoes/arquivos-lote", {
        revisao_ids: [...marcadas.keys()],
      });
      setListaDownload(r);
      setTiposMarcados(new Set(r.arquivos.map((a) => a.tipo)));
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível listar os arquivos.");
      setPainelLote(null);
    }
  }

  async function baixarLote() {
    if (!listaDownload) return;
    const escolhidos = listaDownload.arquivos.filter((a) => tiposMarcados.has(a.tipo));
    if (!escolhidos.length) return;
    const nomeZip = `${obra?.codigo ?? "obra"}-projetos-${new Date().toISOString().slice(0, 10)}.zip`;

    // Chrome e Edge gravam o ZIP direto no disco, à medida que chega; nos
    // outros navegadores ele é montado na memória. O seletor de arquivo tem
    // de abrir antes de qualquer espera, ainda no clique.
    const janela = window as JanelaComSalvar;
    let destino: WritableStream<Uint8Array> | null = null;
    if (janela.showSaveFilePicker) {
      try {
        const arquivo = await janela.showSaveFilePicker({
          suggestedName: nomeZip,
          types: [{ description: "Arquivo ZIP", accept: { "application/zip": [".zip"] } }],
        });
        destino = await arquivo.createWritable();
      } catch {
        return; // a pessoa fechou a janela de salvar
      }
    }

    const controle = new AbortController();
    cancelarDownload.current = controle;
    const falhas: string[] = [];
    const progresso: Progresso = { feitos: 0, total: escolhidos.length, bytes: 0 };
    setBaixando({ ...progresso });
    setResultadoDownload(null);

    // Um arquivo por vez: cada um passa pelo download avulso, que confere a
    // permissão de novo e registra quem baixou.
    async function* entradas() {
      for (const a of escolhidos) {
        if (controle.signal.aborted) return;
        try {
          const d = await api.get<{ url: string }>(`/arquivos/${a.id}/download`);
          const r = await fetch(d.url, { signal: controle.signal });
          if (!r.ok || !r.body) throw new Error(String(r.status));
          const contador = new TransformStream<Uint8Array, Uint8Array>({
            transform(pedaco, saida) {
              progresso.bytes += pedaco.byteLength;
              setBaixando({ ...progresso });
              saida.enqueue(pedaco);
            },
          });
          yield { name: `${a.pasta}/${a.nome}`, input: r.body.pipeThrough(contador) };
        } catch {
          if (controle.signal.aborted) return;
          falhas.push(a.nome);
        }
        progresso.feitos += 1;
        setBaixando({ ...progresso });
      }
    }

    try {
      const zip = downloadZip(entradas());
      if (destino) {
        await zip.body!.pipeTo(destino, { signal: controle.signal });
      } else {
        const blob = await zip.blob();
        if (!controle.signal.aborted) {
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = nomeZip;
          link.click();
          URL.revokeObjectURL(url);
        }
      }
      setResultadoDownload({
        baixados: progresso.feitos - falhas.length,
        falhas,
        cancelado: controle.signal.aborted,
      });
      if (!controle.signal.aborted) setPainelLote(null);
    } catch {
      setResultadoDownload({
        baixados: progresso.feitos - falhas.length,
        falhas,
        cancelado: controle.signal.aborted,
      });
      if (!controle.signal.aborted) setErro("O download foi interrompido. Tente de novo.");
    } finally {
      setBaixando(null);
      cancelarDownload.current = null;
    }
  }

  async function liberarLote() {
    setLiberando(true);
    setErro(null);
    try {
      const r = await api.post<ResultadoLote>("/revisoes/liberar-lote", {
        revisao_ids: marcadasEmRevisao.map(([id]) => id),
        observacao: observacaoLote.trim() || null,
        avisar: avisarLote,
      });
      setResultadoLote(r);
      // Ficam marcadas só as que não saíram, para corrigir e tentar de novo.
      setMarcadas((m) => {
        const novo = new Map(m);
        for (const x of r.liberadas) novo.delete(x.revisao_id);
        return novo;
      });
      setPainelLote(null);
      setObservacaoLote("");
      await consultar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível liberar as revisões.");
    } finally {
      setLiberando(false);
    }
  }

  useEffect(() => {
    consultar();
  }, [consultar]);

  async function exportar() {
    const p = new URLSearchParams();
    if (disciplina) p.set("disciplina_id", disciplina);
    if (fase) p.set("fase_id", fase);
    if (status) p.set("status_revisao", status);

    const r = await fetch(`${api.base}/obras/${obraId}/documentos/exportar?${p}`, {
      headers: { Authorization: `Bearer ${lerToken()}` },
    });
    if (!r.ok) {
      setErro("Não foi possível gerar a lista mestra.");
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `lista-mestra-${obra?.codigo ?? "obra"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const totalPaginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;

  return (
    <>
      {obra && (
        <CapaObra obra={obra} className="capa-acervo">
          <span className="capa-textos">
            <span className="codigo">Obra {obra.codigo}</span>
            <h1 className="nome-obra">{obra.nome}</h1>
            {obra.cliente && <span className="capa-sub">{obra.cliente}</span>}
          </span>
        </CapaObra>
      )}
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Acervo</span>
          <h2 className="titulo-secao">
            Projetos <em>da obra</em>
          </h2>
        </div>
        <div className="linha">
          <div className="seletor-visao" role="group" aria-label="Forma de ver o acervo">
            <button
              className={visao === "lista" ? "ativo" : ""}
              onClick={() => {
                setVisao("lista");
                localStorage.setItem(CHAVE_VISAO, "lista");
              }}
            >
              Lista
            </button>
            <button
              className={visao === "arvore" ? "ativo" : ""}
              onClick={() => {
                setVisao("arvore");
                localStorage.setItem(CHAVE_VISAO, "arvore");
              }}
            >
              Pastas
            </button>
          </div>
          <button className="botao secundario" onClick={exportar}>
            Exportar lista mestra
          </button>
          {obra?.permissoes.includes("enviar") && (
            <Link className="botao" to={`/obras/${obra.id}/enviar`}>
              Enviar arquivos
            </Link>
          )}
        </div>
      </div>

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      {resultadoLote && (
        <Aviso
          tom={resultadoLote.recusadas.length ? "atencao" : "ok"}
          titulo={`${resultadoLote.liberadas.length} revis${resultadoLote.liberadas.length === 1 ? "ão liberada" : "ões liberadas"} para obra${
            resultadoLote.recusadas.length
              ? ` · ${resultadoLote.recusadas.length} não ${resultadoLote.recusadas.length === 1 ? "pôde" : "puderam"} ser liberada${resultadoLote.recusadas.length === 1 ? "" : "s"}`
              : ""
          }`}
          itens={resultadoLote.recusadas.map(
            (x) => `${x.documento ?? "Revisão " + x.revisao_id}${x.revisao ? ` R${x.revisao}` : ""}: ${x.motivos.join(" ")}`,
          )}
        >
          {resultadoLote.recusadas.length > 0 && (
            <div style={{ marginTop: 4, fontSize: 12.5 }}>
              As que não saíram continuam marcadas: corrija e libere de novo.
            </div>
          )}
          <button
            className="botao secundario pequeno"
            style={{ marginTop: 8 }}
            onClick={() => setResultadoLote(null)}
          >
            Fechar
          </button>
        </Aviso>
      )}

      {resultadoDownload && (
        <Aviso
          tom={resultadoDownload.falhas.length || resultadoDownload.cancelado ? "atencao" : "ok"}
          titulo={
            resultadoDownload.cancelado
              ? `Download cancelado · ${resultadoDownload.baixados} arquivo${resultadoDownload.baixados === 1 ? "" : "s"} já baixado${resultadoDownload.baixados === 1 ? "" : "s"}`
              : `${resultadoDownload.baixados} arquivo${resultadoDownload.baixados === 1 ? " baixado" : "s baixados"} no ZIP${
                  resultadoDownload.falhas.length
                    ? ` · ${resultadoDownload.falhas.length} não ${resultadoDownload.falhas.length === 1 ? "veio" : "vieram"}`
                    : ""
                }`
          }
          itens={resultadoDownload.falhas}
        >
          <button
            className="botao secundario pequeno"
            style={{ marginTop: 8 }}
            onClick={() => setResultadoDownload(null)}
          >
            Fechar
          </button>
        </Aviso>
      )}

      {visao === "arvore" ? (
        <div className="folha">
          <Arvore obraId={Number(obraId)} abrir={pastaPedida} />
        </div>
      ) : (
      <div className="folha">
        <div className="folha-corpo">
          <div className="filtros">
            <label className="campo">
              <span className="rotulo">Buscar</span>
              <input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Código ou título"
              />
            </label>
            <label className="campo">
              <span className="rotulo">Disciplina</span>
              <select
                value={disciplina}
                onChange={(e) => {
                  setDisciplina(e.target.value);
                  setPagina(1);
                }}
              >
                <option value="">Todas</option>
                {disciplinas.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.codigo} · {d.nome}
                  </option>
                ))}
              </select>
            </label>
            <label className="campo">
              <span className="rotulo">Fase</span>
              <select
                value={fase}
                onChange={(e) => {
                  setFase(e.target.value);
                  setPagina(1);
                }}
              >
                <option value="">Todas</option>
                {fases.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.codigo} · {f.nome}
                  </option>
                ))}
              </select>
            </label>
            <label className="campo">
              <span className="rotulo">Status</span>
              <select
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value as StatusRevisao | "");
                  setPagina(1);
                }}
              >
                <option value="">Todos</option>
                <option value="liberado_para_obra">Liberado para obra</option>
                <option value="em_revisao">Em revisão</option>
                <option value="obsoleto">Obsoleto</option>
                <option value="reprovado">Reprovada</option>
                <option value="cancelado">Cancelado</option>
              </select>
            </label>
            <label className="campo">
              <span className="rotulo">Formato</span>
              <select
                value={tipo}
                onChange={(e) => {
                  setTipo(e.target.value as TipoArquivo | "");
                  setPagina(1);
                }}
              >
                <option value="">Todos</option>
                <option value="dwg">DWG</option>
                <option value="rvt">RVT</option>
                <option value="pdf">PDF</option>
                <option value="ifc">IFC</option>
              </select>
            </label>
          </div>
        </div>

        {carregando && !dados ? (
          <Carregando />
        ) : !dados || dados.itens.length === 0 ? (
          <Vazio titulo="Nenhum documento encontrado">
            {buscaAplicada || disciplina || fase || status || tipo
              ? "Ajuste os filtros para ver outros documentos."
              : "Envie o primeiro arquivo para começar o acervo desta obra."}
          </Vazio>
        ) : (
          <>
            {marcadas.size === 0 && (
              <p className="silencioso dica-lote">
                Marque as linhas para baixar vários projetos de uma vez
                {podeLiberar && (
                  <>
                    {" "}ou liberá-los para obra (filtre <strong>Status: Em revisão</strong> para achar
                    os que aguardam análise)
                  </>
                )}
                .
              </p>
            )}
            <div className="tabela-rolagem">
              <table className="tabela">
                <thead>
                  <tr>
                    <th className="col-marca">
                      {(() => {
                        const elegiveis = dados.itens.filter((d) => d.revisao_atual);
                        const todas =
                          elegiveis.length > 0 &&
                          elegiveis.every((d) => d.revisao_atual && marcadas.has(d.revisao_atual.id));
                        return (
                          <input
                            type="checkbox"
                            aria-label="Marcar todos os documentos desta página"
                            title="Marcar todos os documentos desta página"
                            disabled={elegiveis.length === 0}
                            checked={todas}
                            onChange={() => alternarPagina(!todas)}
                          />
                        );
                      })()}
                    </th>
                    <th>Documento</th>
                    <th>Título</th>
                    <th>Disc.</th>
                    <th>Fase</th>
                    <th>Rev.</th>
                    <th>Status</th>
                    <th>Liberada em</th>
                    <th>Revisões</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.itens.map((d) => (
                    <tr
                      key={d.id}
                      className={d.revisao_atual && marcadas.has(d.revisao_atual.id) ? "marcada" : undefined}
                    >
                      <td className="col-marca">
                        {d.revisao_atual && (
                          <input
                            type="checkbox"
                            aria-label={`Marcar ${d.codigo} R${d.revisao_atual.numero}`}
                            checked={marcadas.has(d.revisao_atual.id)}
                            onChange={() => alternar(d)}
                          />
                        )}
                      </td>
                      <td>
                        <Link className="link-doc" to={`/documentos/${d.id}`}>
                          {d.codigo}
                        </Link>
                      </td>
                      <td className="titulo-lista">
                        {d.titulo ?? <span className="sem">Sem título</span>}
                      </td>
                      <td className="mono silencioso">{d.disciplina.codigo}</td>
                      <td className="mono silencioso">{d.fase.codigo}</td>
                      <td className="mono">
                        {d.revisao_atual ? `R${d.revisao_atual.numero}` : "—"}
                      </td>
                      <td>
                        <span className="linha" style={{ gap: 6, flexWrap: "nowrap" }}>
                          {d.revisao_atual && <Estado status={d.revisao_atual.status} />}
                          <MarcaSolicitada
                            quantidade={d.solicitacoes_abertas}
                            autorizadas={d.solicitacoes_autorizadas}
                          />
                        </span>
                      </td>
                      <td className="mono silencioso" style={{ fontSize: 12 }}>
                        {formatarData(d.revisao_atual?.publicada_em ?? null, false)}
                      </td>
                      <td className="mono silencioso">{d.total_revisoes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="paginacao">
              <span>
                {dados.total} documento{dados.total === 1 ? "" : "s"}
                {totalPaginas > 1 && ` · página ${dados.pagina} de ${totalPaginas}`}
              </span>
              <label className="linha" style={{ gap: 6, fontSize: 12.5 }}>
                <span className="silencioso">Por página</span>
                <select
                  value={porPagina}
                  onChange={(e) => {
                    setPorPagina(Number(e.target.value));
                    setPagina(1);
                  }}
                >
                  {TAMANHOS_PAGINA.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              {totalPaginas > 1 && (
                <div className="linha">
                  <button
                    className="botao secundario pequeno"
                    disabled={pagina <= 1}
                    onClick={() => setPagina((p) => p - 1)}
                  >
                    Anterior
                  </button>
                  <button
                    className="botao secundario pequeno"
                    disabled={pagina >= totalPaginas}
                    onClick={() => setPagina((p) => p + 1)}
                  >
                    Próxima
                  </button>
                </div>
              )}
            </div>
          </>
        )}

        {marcadas.size > 0 && (
          <div className="barra-lote" role="region" aria-label="Ações em lote">
            {painelLote === null ? (
              <div className="linha">
                <strong>
                  {marcadas.size} documento{marcadas.size === 1 ? " marcado" : "s marcados"}
                </strong>
                <span className="silencioso" style={{ fontSize: 12 }}>
                  {[...marcadas.values()]
                    .slice(0, 4)
                    .map((m) => `${m.documento} R${m.numero}`)
                    .join(", ")}
                  {marcadas.size > 4 && "…"}
                </span>
                <div className="espaco" />
                <button
                  className="botao secundario pequeno"
                  onClick={() => setMarcadas(new Map())}
                >
                  Desmarcar
                </button>
                <button className="botao secundario" onClick={abrirDownload}>
                  Baixar…
                </button>
                {podeLiberar && (
                  <button
                    className="botao"
                    disabled={marcadasEmRevisao.length === 0}
                    title={
                      marcadasEmRevisao.length === 0 ? "Nenhuma das marcadas está em revisão" : undefined
                    }
                    onClick={() => setPainelLote("liberar")}
                  >
                    Liberar para obra…
                  </button>
                )}
              </div>
            ) : painelLote === "baixar" ? (
              <PainelDownload
                lista={listaDownload}
                tipos={tiposMarcados}
                aoMudarTipos={setTiposMarcados}
                baixando={baixando}
                aoBaixar={baixarLote}
                aoCancelar={() => cancelarDownload.current?.abort()}
                aoVoltar={() => setPainelLote(null)}
              />
            ) : (
              <div>
                <strong>
                  Liberar {marcadasEmRevisao.length} revis{marcadasEmRevisao.length === 1 ? "ão" : "ões"} para
                  obra
                </strong>
                {marcadasEmRevisao.length < marcadas.size && (
                  <p className="silencioso" style={{ fontSize: 12.5, margin: "4px 0 0" }}>
                    Só as marcadas em revisão entram; as outras{" "}
                    {marcadas.size - marcadasEmRevisao.length} continuam marcadas.
                  </p>
                )}
                <p className="silencioso" style={{ fontSize: 12.5, margin: "4px 0 8px" }}>
                  Cada uma passa pelas mesmas conferências da liberação avulsa (o DWG precisa do PDF,
                  por exemplo); as que não puderem sair voltam com o motivo, e as outras são
                  liberadas. Pedidos de revisão autorizados desses documentos fecham como atendidos.
                </p>
                <label className="campo" style={{ display: "block" }}>
                  <span className="rotulo">Observação (opcional, vale para todas)</span>
                  <textarea
                    value={observacaoLote}
                    onChange={(e) => setObservacaoLote(e.target.value)}
                    maxLength={4000}
                    rows={2}
                    disabled={liberando}
                    placeholder="Ex.: Liberação do acervo migrado do Mobuss."
                  />
                </label>
                <label className="opcao-aviso">
                  <input
                    type="checkbox"
                    checked={avisarLote}
                    onChange={(e) => setAvisarLote(e.target.checked)}
                    disabled={liberando}
                  />
                  Avisar a obra (uma notificação e um e-mail por revisão)
                  <span className="silencioso">— desmarque para liberar em volume sem e-mails</span>
                </label>
                <div className="linha" style={{ marginTop: 10 }}>
                  <button className="botao" disabled={liberando} onClick={liberarLote}>
                    {liberando ? "Liberando…" : `Liberar ${marcadasEmRevisao.length} para obra`}
                  </button>
                  <button
                    className="botao secundario pequeno"
                    disabled={liberando}
                    onClick={() => setPainelLote(null)}
                  >
                    Voltar
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      )}
    </>
  );
}

/** Escolha dos formatos e andamento do download em lote. */
function PainelDownload({
  lista,
  tipos,
  aoMudarTipos,
  baixando,
  aoBaixar,
  aoCancelar,
  aoVoltar,
}: {
  lista: ListaDownload | null;
  tipos: Set<string>;
  aoMudarTipos: (t: Set<string>) => void;
  baixando: Progresso | null;
  aoBaixar: () => void;
  aoCancelar: () => void;
  aoVoltar: () => void;
}) {
  if (!lista) {
    return (
      <p className="silencioso" style={{ margin: 0 }}>
        Listando os arquivos…
      </p>
    );
  }
  const porTipo = new Map<string, { quantidade: number; bytes: number }>();
  for (const a of lista.arquivos) {
    const t = porTipo.get(a.tipo) ?? { quantidade: 0, bytes: 0 };
    t.quantidade += 1;
    t.bytes += a.tamanho ?? 0;
    porTipo.set(a.tipo, t);
  }
  const presentes = ORDEM_TIPO.filter((t) => porTipo.has(t));
  const escolhidos = lista.arquivos.filter((a) => tipos.has(a.tipo));
  const totalBytes = escolhidos.reduce((s, a) => s + (a.tamanho ?? 0), 0);
  const comAviso = new Set(escolhidos.filter((a) => a.aviso).map((a) => a.documento)).size;
  const naMemoria = !(window as JanelaComSalvar).showSaveFilePicker;

  if (baixando) {
    const parte = totalBytes
      ? Math.min(1, baixando.bytes / totalBytes)
      : baixando.feitos / Math.max(1, baixando.total);
    return (
      <div>
        <strong>
          Baixando {Math.min(baixando.feitos + 1, baixando.total)} de {baixando.total} arquivos
        </strong>
        <div
          className="progresso-lote"
          role="progressbar"
          aria-valuenow={Math.round(parte * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span style={{ width: `${parte * 100}%` }} />
        </div>
        <div className="linha">
          <span className="silencioso" style={{ fontSize: 12.5 }}>
            {tamanhoLegivel(baixando.bytes)} de {tamanhoLegivel(totalBytes)}
          </span>
          <div className="espaco" />
          <button className="botao secundario pequeno" onClick={aoCancelar}>
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <strong>Baixar os projetos marcados</strong>
      {lista.arquivos.length === 0 ? (
        <p className="silencioso" style={{ fontSize: 12.5, margin: "4px 0 8px" }}>
          Nenhum arquivo disponível nos documentos marcados.
        </p>
      ) : (
        <>
          <p className="silencioso" style={{ fontSize: 12.5, margin: "4px 0 8px" }}>
            Escolha os formatos. Sai um ZIP com uma pasta por disciplina; cada arquivo baixado fica
            no registro de atividades, como no download avulso.
          </p>
          <div className="linha" style={{ gap: 14, flexWrap: "wrap" }}>
            {presentes.map((t) => {
              const info = porTipo.get(t)!;
              return (
                <label key={t} className="opcao-aviso" style={{ margin: 0 }}>
                  <input
                    type="checkbox"
                    checked={tipos.has(t)}
                    onChange={(e) => {
                      const novo = new Set(tipos);
                      if (e.target.checked) novo.add(t);
                      else novo.delete(t);
                      aoMudarTipos(novo);
                    }}
                  />
                  <strong>{ROTULO_TIPO[t] ?? t.toUpperCase()}</strong>
                  <span className="silencioso">
                    {info.quantidade} arquivo{info.quantidade === 1 ? "" : "s"} ·{" "}
                    {tamanhoLegivel(info.bytes)}
                  </span>
                </label>
              );
            })}
          </div>
        </>
      )}
      {comAviso > 0 && (
        <p style={{ fontSize: 12.5, margin: "8px 0 0" }}>
          <strong>Atenção:</strong>{" "}
          {comAviso === 1
            ? "1 documento marcado não está liberado para obra"
            : `${comAviso} documentos marcados não estão liberados para obra`}{" "}
          (em revisão, reprovado ou obsoleto). Não use para execução.
        </p>
      )}
      {lista.recusadas.length > 0 && (
        <p className="silencioso" style={{ fontSize: 12.5, margin: "8px 0 0" }}>
          Fora do download:{" "}
          {lista.recusadas
            .map(
              (r) =>
                `${r.documento ?? "revisão " + r.revisao_id}${r.revisao ? ` R${r.revisao}` : ""} (${r.motivos.join(" ")})`,
            )
            .join("; ")}
        </p>
      )}
      {naMemoria && totalBytes > 1024 ** 3 && (
        <p style={{ fontSize: 12.5, margin: "8px 0 0" }}>
          Este navegador monta o ZIP na memória: para mais de 1 GB, prefira o Chrome ou o Edge.
        </p>
      )}
      <div className="linha" style={{ marginTop: 10 }}>
        <button className="botao" disabled={escolhidos.length === 0} onClick={aoBaixar}>
          Baixar {escolhidos.length} arquivo{escolhidos.length === 1 ? "" : "s"}
          {totalBytes > 0 && ` (${tamanhoLegivel(totalBytes)})`}
        </button>
        <button className="botao secundario pequeno" onClick={aoVoltar}>
          Voltar
        </button>
      </div>
    </div>
  );
}
