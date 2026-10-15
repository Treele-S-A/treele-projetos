import { useCallback, useEffect, useState } from "react";
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

/** Revisão marcada para liberar em lote — guarda o que a tela mostra dela. */
interface Marcada {
  documento: string;
  numero: string;
}

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
  const [painelLote, setPainelLote] = useState(false);
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

  /** Linha que pode entrar no lote: a revisão atual está em análise. */
  function liberavel(d: Documento): boolean {
    return podeLiberar && d.revisao_atual?.status === "em_revisao";
  }

  function alternar(d: Documento) {
    const rev = d.revisao_atual;
    if (!rev) return;
    setMarcadas((m) => {
      const novo = new Map(m);
      if (novo.has(rev.id)) novo.delete(rev.id);
      else novo.set(rev.id, { documento: d.codigo, numero: rev.numero });
      return novo;
    });
  }

  function alternarPagina(marcar: boolean) {
    if (!dados) return;
    setMarcadas((m) => {
      const novo = new Map(m);
      for (const d of dados.itens) {
        if (!liberavel(d) || !d.revisao_atual) continue;
        if (marcar) novo.set(d.revisao_atual.id, { documento: d.codigo, numero: d.revisao_atual.numero });
        else novo.delete(d.revisao_atual.id);
      }
      return novo;
    });
  }

  async function liberarLote() {
    setLiberando(true);
    setErro(null);
    try {
      const r = await api.post<ResultadoLote>("/revisoes/liberar-lote", {
        revisao_ids: [...marcadas.keys()],
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
      setPainelLote(false);
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
            {podeLiberar && status !== "em_revisao" && marcadas.size === 0 && (
              <p className="silencioso dica-lote">
                Para liberar várias revisões de uma vez, filtre <strong>Status: Em revisão</strong> e
                marque as linhas.
              </p>
            )}
            <div className="tabela-rolagem">
              <table className="tabela">
                <thead>
                  <tr>
                    {podeLiberar && (
                      <th className="col-marca">
                        {(() => {
                          const elegiveis = dados.itens.filter(liberavel);
                          const todas =
                            elegiveis.length > 0 &&
                            elegiveis.every((d) => d.revisao_atual && marcadas.has(d.revisao_atual.id));
                          return (
                            <input
                              type="checkbox"
                              aria-label="Marcar todas as revisões em revisão desta página"
                              title="Marcar todas as revisões em revisão desta página"
                              disabled={elegiveis.length === 0}
                              checked={todas}
                              onChange={() => alternarPagina(!todas)}
                            />
                          );
                        })()}
                      </th>
                    )}
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
                      {podeLiberar && (
                        <td className="col-marca">
                          {liberavel(d) && d.revisao_atual && (
                            <input
                              type="checkbox"
                              aria-label={`Marcar ${d.codigo} R${d.revisao_atual.numero} para liberar`}
                              checked={marcadas.has(d.revisao_atual.id)}
                              onChange={() => alternar(d)}
                            />
                          )}
                        </td>
                      )}
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

        {podeLiberar && marcadas.size > 0 && (
          <div className="barra-lote" role="region" aria-label="Liberação em lote">
            {!painelLote ? (
              <div className="linha">
                <strong>
                  {marcadas.size} revis{marcadas.size === 1 ? "ão marcada" : "ões marcadas"}
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
                <button className="botao" onClick={() => setPainelLote(true)}>
                  Liberar para obra…
                </button>
              </div>
            ) : (
              <div>
                <strong>
                  Liberar {marcadas.size} revis{marcadas.size === 1 ? "ão" : "ões"} para obra
                </strong>
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
                    {liberando ? "Liberando…" : `Liberar ${marcadas.size} para obra`}
                  </button>
                  <button
                    className="botao secundario pequeno"
                    disabled={liberando}
                    onClick={() => setPainelLote(false)}
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
