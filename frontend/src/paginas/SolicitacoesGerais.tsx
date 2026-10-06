import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ErroApi, formatarData, type SolicitacaoGeral } from "../api";
import { Aviso, Carregando, Vazio } from "../componentes";
import { SituacaoSolicitacao } from "../Solicitacoes";
import { useSessao } from "../sessao";

type Filtro = "todas" | "aberta" | "autorizada" | "atendida" | "recusada";

const FILTROS: Array<[Filtro, string]> = [
  ["todas", "Todas"],
  ["aberta", "Aguardando autorização"],
  ["autorizada", "Autorizadas"],
  ["atendida", "Atendidas"],
  ["recusada", "Recusadas"],
];

/** Os pedidos de revisão de todas as obras, para o administrador (06/10/2026).
 *  Cada item leva ao documento, já no pedido. */
export default function SolicitacoesGerais() {
  const { obras } = useSessao();
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [obraId, setObraId] = useState("");
  const [lista, setLista] = useState<SolicitacaoGeral[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    setLista(null);
    setErro(null);
    const parametros = new URLSearchParams();
    if (filtro !== "todas") parametros.set("status", filtro);
    if (obraId) parametros.set("obra_id", obraId);
    const consulta = parametros.toString();
    api
      .get<SolicitacaoGeral[]>(`/solicitacoes${consulta ? `?${consulta}` : ""}`)
      .then((r) => vivo && setLista(r))
      .catch(
        (ex) =>
          vivo &&
          setErro(ex instanceof ErroApi ? ex.message : "Não foi possível carregar as solicitações."),
      );
    return () => {
      vivo = false;
    };
  }, [filtro, obraId]);

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Todas as obras</span>
          <h1>Solicitações de revisão</h1>
        </div>
      </div>

      <div className="folha">
        <div className="folha-corpo">
          <div className="filtros-solicitacoes">
            <div className="seletor-visao" role="group" aria-label="Situação">
              {FILTROS.map(([valor, rotulo]) => (
                <button
                  key={valor}
                  className={filtro === valor ? "ativo" : ""}
                  onClick={() => setFiltro(valor)}
                >
                  {rotulo}
                </button>
              ))}
            </div>
            <label className="campo">
              <span className="rotulo">Obra</span>
              <select value={obraId} onChange={(e) => setObraId(e.target.value)}>
                <option value="">Todas</option>
                {obras.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.codigo} · {o.nome}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {erro && (
          <div className="folha-corpo">
            <Aviso tom="erro">{erro}</Aviso>
          </div>
        )}
        {lista === null && !erro && <Carregando texto="Buscando as solicitações" />}
        {lista?.length === 0 && (
          <Vazio titulo="Nenhuma solicitação">
            <span className="silencioso">Nada com esse filtro.</span>
          </Vazio>
        )}

        {lista && lista.length > 0 && (
          <div className="lista-solicitacoes">
            {lista.map((s) => (
              <Link
                key={s.id}
                to={`/documentos/${s.documento_id}#solicitacao-${s.id}`}
                className="item-solicitacao"
                title="Abrir o documento, no pedido"
              >
                <span className="item-topo">
                  <SituacaoSolicitacao status={s.status} />
                  <span className="mono silencioso">{s.obra_codigo}</span>
                  <span className="silencioso">{s.obra_nome}</span>
                </span>
                <span className="doc-na-pasta">
                  <span className="codigo mono">
                    {s.documento_codigo}
                    {s.revisao_numero ? ` · sobre a R${s.revisao_numero}` : ""}
                  </span>
                  <span className={s.documento_titulo ? "titulo" : "titulo sem"}>
                    {s.documento_titulo ?? "Sem título"}
                  </span>
                </span>
                <span className="item-descricao">{s.descricao}</span>
                <span className="silencioso item-rodape">
                  {s.criada_por ? `${s.criada_por.nome} · ` : ""}
                  {formatarData(s.criada_em)}
                  {s.anexos.length > 0 &&
                    ` · ${s.anexos.length} anexo${s.anexos.length === 1 ? "" : "s"}`}
                  {s.status === "atendida" && s.atendida_por_numero
                    ? ` · atendida pela R${s.atendida_por_numero}`
                    : ""}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
