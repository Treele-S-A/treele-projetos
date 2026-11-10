import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ErroApi, formatarData, type Evento, type Pagina } from "../api";
import { Aviso, Carregando, Vazio } from "../componentes";

const ROTULO_ACAO: Record<string, string> = {
  login: "Entrou no sistema",
  acesso: "Voltou com a sessão aberta",
  download: "Baixou arquivo",
  visualizacao: "Visualizou arquivo",
  lido_pelo_assistente: "Arquivo lido pelo assistente",
  upload_iniciado: "Começou envio",
  upload_concluido: "Concluiu envio",
  arquivo_removido: "Excluiu arquivo",
  revisao_excluida: "Excluiu revisão",
  revisao_solicitada: "Pediu revisão",
  revisao_autorizada: "Autorizou revisão",
  revisao_recusada: "Recusou revisão",
  revisao_publicada: "Liberou para obra",
  revisao_reprovada: "Reprovou revisão",
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
  ata_analise_registrada: "Registrou ata de análise crítica",
  membro_papel_alterado: "Trocou o papel na equipe",
  conjunto_conflito_criado: "Criou conjunto de conflitos",
  conjunto_conflito_alterado: "Alterou conjunto de conflitos",
  conjunto_conflito_apagado: "Apagou conjunto de conflitos",
  conflitos_detectados: "Detectou conflitos",
  conflito_alterado: "Alterou conflito",
  vista_criada: "Criou vista do 3D",
  cronograma_criado: "Criou o cronograma",
  cronograma_apagado: "Apagou o cronograma",
  fornecedor_avaliado: "Avaliou fornecedor",
};

function descrever(e: Evento): string {
  const d = e.detalhes as Record<string, string | string[] | undefined>;
  const partes: string[] = [];
  if (d.documento) partes.push(String(d.documento));
  if (d.revisao) partes.push(`R${d.revisao}`);
  if (d.arquivo) partes.push(String(d.arquivo));
  if (d.ata) partes.push(String(d.ata));
  if (d.titulo) partes.push(String(d.titulo));
  if (d.nome) partes.push(String(d.nome));
  if (d.razao_social) partes.push(String(d.razao_social));
  const n = e.detalhes as Record<string, unknown>;
  if (typeof n.encontrados === "number") {
    partes.push(`${n.encontrados} encontrados, ${n.novos} novos, ${n.resolvidos} resolvidos`);
  }
  if (e.acao === "ata_analise_registrada" && d.resultado) {
    partes.push(d.resultado === "conforme" ? "conforme" : "não conforme");
  }
  if (Array.isArray(d.obsoletadas) && d.obsoletadas.length > 0) {
    partes.push(`tornou obsoleta ${d.obsoletadas.map((r) => `R${r}`).join(", ")}`);
  }
  // "situacao_revisao": nome que os downloads usaram por um dia (02/10/2026).
  const situacao = d.status_revisao ?? (e.acao === "download" ? d.situacao_revisao : undefined);
  if (situacao === "obsoleto") partes.push("⚠ revisão obsoleta");
  if (d.restaurada) partes.push(`R${d.restaurada} voltou a valer`);
  if (d.observacao) partes.push(`“${String(d.observacao)}”`);
  // Exclusões de antes de 09/10/2026, quando ainda se excluía revisão.
  if (e.acao === "revisao_excluida") {
    const arquivos = Array.isArray(d.arquivos) ? d.arquivos : [];
    if (arquivos.length > 0) partes.push(arquivos.join(", "));
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
    setErro(null);
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
