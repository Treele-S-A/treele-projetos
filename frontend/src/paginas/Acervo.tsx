import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
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
import { Aviso, Carregando, Estado, LogoObra, Vazio } from "../componentes";
import { useSessao } from "../sessao";

const POR_PAGINA = 50;
const CHAVE_VISAO = "treele.acervo.visao";

type Visao = "lista" | "arvore";

export default function Acervo() {
  const { obraId } = useParams();
  const { obras, disciplinas, fases } = useSessao();
  const obra = obras.find((o) => o.id === Number(obraId));

  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [disciplina, setDisciplina] = useState("");
  const [fase, setFase] = useState("");
  const [status, setStatus] = useState<StatusRevisao | "">("");
  const [tipo, setTipo] = useState<TipoArquivo | "">("");
  const [pagina, setPagina] = useState(1);
  const [visao, setVisao] = useState<Visao>(
    () => (localStorage.getItem(CHAVE_VISAO) as Visao) || "lista",
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
    const p = new URLSearchParams({ pagina: String(pagina), por_pagina: String(POR_PAGINA) });
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
  }, [obraId, visao, pagina, buscaAplicada, disciplina, fase, status, tipo]);

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
      <div className="cabecalho-area">
        <div className="cabecalho-obra">
          {obra && <LogoObra obra={obra} className="logo-cabecalho" />}
          <div>
            <span className="rotulo">{obra ? `Obra ${obra.codigo}` : "Obra"}</span>
            <h1>{obra?.nome ?? "Acervo"}</h1>
          </div>
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

      {visao === "arvore" ? (
        <div className="folha">
          <Arvore obraId={Number(obraId)} />
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
            <div className="tabela-rolagem">
              <table className="tabela">
                <thead>
                  <tr>
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
                    <tr key={d.id}>
                      <td>
                        <Link className="link-doc" to={`/documentos/${d.id}`}>
                          {d.codigo}
                        </Link>
                      </td>
                      <td>{d.titulo ?? <span className="silencioso">—</span>}</td>
                      <td className="mono silencioso">{d.disciplina.codigo}</td>
                      <td className="mono silencioso">{d.fase.codigo}</td>
                      <td className="mono">
                        {d.revisao_atual ? `R${d.revisao_atual.numero}` : "—"}
                      </td>
                      <td>{d.revisao_atual && <Estado status={d.revisao_atual.status} />}</td>
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
      </div>
      )}
    </>
  );
}
