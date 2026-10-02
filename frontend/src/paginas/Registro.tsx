import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ErroApi, formatarData, type Evento, type Pagina } from "../api";
import { Aviso, Carregando, Vazio } from "../componentes";

const ROTULO_ACAO: Record<string, string> = {
  login: "Entrou no sistema",
  download: "Baixou arquivo",
  visualizacao: "Visualizou arquivo",
  upload_iniciado: "Começou envio",
  upload_concluido: "Concluiu envio",
  arquivo_removido: "Excluiu arquivo",
  revisao_excluida: "Excluiu revisão",
  revisao_solicitada: "Pediu revisão",
  revisao_publicada: "Liberou para obra",
  revisao_cancelada: "Cancelou revisão",
  revisao_atualizada: "Editou descrição",
  documento_atualizado: "Editou documento",
  obra_criada: "Criou a obra",
  obra_atualizada: "Alterou a obra",
  obra_logo_alterado: "Trocou o logo",
  obra_logo_removido: "Removeu o logo",
  membro_adicionado: "Incluiu na equipe",
  membro_removido: "Removeu da equipe",
  padrao_definido: "Alterou a nomenclatura",
  lista_mestra_exportada: "Exportou lista mestra",
};

function descrever(e: Evento): string {
  const d = e.detalhes as Record<string, string | string[] | undefined>;
  const partes: string[] = [];
  if (d.documento) partes.push(String(d.documento));
  if (d.revisao) partes.push(`R${d.revisao}`);
  if (d.arquivo) partes.push(String(d.arquivo));
  if (Array.isArray(d.obsoletadas) && d.obsoletadas.length > 0) {
    partes.push(`tornou obsoleta ${d.obsoletadas.map((r) => `R${r}`).join(", ")}`);
  }
  // "situacao_revisao": nome que os downloads usaram por um dia (02/10/2026).
  const situacao = d.status_revisao ?? (e.acao === "download" ? d.situacao_revisao : undefined);
  if (situacao === "obsoleto") partes.push("⚠ revisão obsoleta");
  if (e.acao === "revisao_excluida") {
    const arquivos = Array.isArray(d.arquivos) ? d.arquivos : [];
    if (arquivos.length > 0) partes.push(arquivos.join(", "));
    if (d.restaurada) partes.push(`R${d.restaurada} voltou a valer`);
    if ((e.detalhes as Record<string, unknown>).documento_excluido === true) {
      partes.push("documento saiu do acervo");
    }
  }
  if ((e.detalhes as Record<string, unknown>).apos_liberacao === true) {
    partes.push("acrescentado após a liberação");
  }
  return partes.join(" · ");
}

export default function Registro() {
  const { obraId } = useParams();
  const [dados, setDados] = useState<Pagina<Evento> | null>(null);
  const [acao, setAcao] = useState("");
  const [pagina, setPagina] = useState(1);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    const p = new URLSearchParams({ pagina: String(pagina), por_pagina: "50" });
    if (acao) p.set("acao", acao);
    setCarregando(true);
    api
      .get<Pagina<Evento>>(`/obras/${obraId}/eventos?${p}`)
      .then(setDados)
      .catch((ex) =>
        setErro(ex instanceof ErroApi ? ex.message : "Não foi possível carregar o registro."),
      )
      .finally(() => setCarregando(false));
  }, [obraId, acao, pagina]);

  const totalPaginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Auditoria</span>
          <h1>Registro de atividades</h1>
        </div>
      </div>

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      <Aviso tom="info">
        Toda leitura e toda alteração ficam registradas, inclusive quem baixou qual revisão e
        quando. É o que responde a discussão de "a obra executou com projeto vencido".
      </Aviso>

      <div className="folha">
        <div className="folha-corpo">
          <label className="campo" style={{ maxWidth: 280 }}>
            <span className="rotulo">Filtrar por ação</span>
            <select
              value={acao}
              onChange={(e) => {
                setAcao(e.target.value);
                setPagina(1);
              }}
            >
              <option value="">Todas</option>
              {Object.entries(ROTULO_ACAO).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>

        {carregando && !dados ? (
          <Carregando />
        ) : !dados || dados.itens.length === 0 ? (
          <Vazio titulo="Nada registrado ainda" />
        ) : (
          <>
            <div className="tabela-rolagem">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Quando</th>
                    <th>Quem</th>
                    <th>Ação</th>
                    <th>Detalhe</th>
                    <th>IP</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.itens.map((e) => (
                    <tr key={e.id}>
                      <td className="mono" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                        {formatarData(e.criado_em)}
                      </td>
                      <td>{e.usuario?.nome ?? "—"}</td>
                      <td>{ROTULO_ACAO[e.acao] ?? e.acao}</td>
                      <td className="mono silencioso" style={{ fontSize: 12 }}>
                        {descrever(e)}
                      </td>
                      <td className="mono silencioso" style={{ fontSize: 11 }}>
                        {e.ip ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="paginacao">
              <span>
                {dados.total} registro{dados.total === 1 ? "" : "s"}
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
    </>
  );
}
