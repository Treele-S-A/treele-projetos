import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ErroApi, formatarData, type AtaLinha, type Pagina } from "../api";
import { Aviso, Carregando, Vazio } from "../componentes";
import { useSessao } from "../sessao";

type Filtro = "todas" | "conforme" | "nao_conforme";

const FILTROS: Array<[Filtro, string]> = [
  ["todas", "Todas"],
  ["conforme", "Conformes"],
  ["nao_conforme", "Não conformes"],
];

/** As atas de análise crítica (PRO-FL-005) das obras da pessoa (TREELE,
 *  29/10/2026): o registro que o SIAC pede de cada liberação. */
export default function Atas() {
  const { obras, disciplinas } = useSessao();
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [obraId, setObraId] = useState("");
  const [disciplinaId, setDisciplinaId] = useState("");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<Pagina<AtaLinha> | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    setDados(null);
    setErro(null);
    const p = new URLSearchParams({ pagina: String(pagina), por_pagina: "50" });
    if (filtro !== "todas") p.set("resultado", filtro);
    if (obraId) p.set("obra_id", obraId);
    if (disciplinaId) p.set("disciplina_id", disciplinaId);
    if (buscaAplicada) p.set("busca", buscaAplicada);
    api
      .get<Pagina<AtaLinha>>(`/atas?${p}`)
      .then((r) => vivo && setDados(r))
      .catch((ex) => vivo && setErro(ex instanceof ErroApi ? ex.message : "Não foi possível carregar as atas."));
    return () => {
      vivo = false;
    };
  }, [filtro, obraId, disciplinaId, buscaAplicada, pagina]);

  const totalPaginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Análise crítica · PRO-FL-005</span>
          <h1>Atas de análise crítica</h1>
        </div>
      </div>

      <div className="folha">
        <div className="folha-corpo">
          <div className="filtros-solicitacoes">
            <div className="seletor-visao" role="group" aria-label="Resultado">
              {FILTROS.map(([valor, rotulo]) => (
                <button
                  key={valor}
                  className={filtro === valor ? "ativo" : ""}
                  onClick={() => {
                    setFiltro(valor);
                    setPagina(1);
                  }}
                >
                  {rotulo}
                </button>
              ))}
            </div>
            <label className="campo">
              <span className="rotulo">Obra</span>
              <select
                value={obraId}
                onChange={(e) => {
                  setObraId(e.target.value);
                  setPagina(1);
                }}
              >
                <option value="">Todas</option>
                {obras.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.codigo} · {o.nome}
                  </option>
                ))}
              </select>
            </label>
            <label className="campo">
              <span className="rotulo">Disciplina</span>
              <select
                value={disciplinaId}
                onChange={(e) => {
                  setDisciplinaId(e.target.value);
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
            <form
              className="campo"
              onSubmit={(e) => {
                e.preventDefault();
                setBuscaAplicada(busca.trim());
                setPagina(1);
              }}
            >
              <span className="rotulo">Documento</span>
              <input
                type="search"
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                onBlur={() => setBuscaAplicada(busca.trim())}
                placeholder="Ex.: UNO-HID-PE-001"
              />
            </form>
          </div>
        </div>

        {erro && (
          <div className="folha-corpo">
            <Aviso tom="erro">{erro}</Aviso>
          </div>
        )}
        {dados === null && !erro && <Carregando texto="Buscando as atas" />}
        {dados && dados.itens.length === 0 && (
          <Vazio titulo="Nenhuma ata aqui">
            As atas nascem ao liberar revisões para obra: o checklist de análise crítica é preenchido antes.
          </Vazio>
        )}
        {dados && dados.itens.length > 0 && (
          <div className="tabela-rolagem">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Ata</th>
                  <th>Obra</th>
                  <th>Disciplina</th>
                  <th>Revisões</th>
                  <th>Resultado</th>
                  <th>Por</th>
                  <th>Data</th>
                </tr>
              </thead>
              <tbody>
                {dados.itens.map((a) => (
                  <tr key={a.id}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <Link className="link-doc mono" to={`/atas/${a.id}`}>
                        {a.codigo}
                      </Link>
                    </td>
                    <td>{a.obra}</td>
                    <td>{a.disciplina}</td>
                    <td className="titulo-lista mono" style={{ whiteSpace: "nowrap" }} title={a.revisoes.map((r) => `${r.documento} R${r.revisao}`).join("\n")}>
                      {a.revisoes.length === 1
                        ? `${a.revisoes[0].documento} R${a.revisoes[0].revisao}`
                        : `${a.revisoes[0].documento} R${a.revisoes[0].revisao} e mais ${a.revisoes.length - 1}`}
                    </td>
                    <td>
                      <span className={`resultado-ata ${a.resultado}`}>
                        {a.resultado === "conforme" ? "Conforme" : `Não conforme (${a.nao_conformes})`}
                      </span>
                    </td>
                    <td>{a.criada_por ?? "—"}</td>
                    <td className="mono" style={{ whiteSpace: "nowrap" }}>
                      {formatarData(a.criada_em)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {dados && totalPaginas > 1 && (
          <div className="folha-corpo linha" style={{ gap: 8 }}>
            <button className="botao secundario pequeno" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>
              Anterior
            </button>
            <span className="silencioso" style={{ fontSize: 12.5 }}>
              Página {pagina} de {totalPaginas} · {dados.total} atas
            </span>
            <button
              className="botao secundario pequeno"
              disabled={pagina >= totalPaginas}
              onClick={() => setPagina(pagina + 1)}
            >
              Próxima
            </button>
          </div>
        )}
      </div>
    </>
  );
}
