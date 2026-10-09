/** Histórico de revisões de um documento.
 *
 * Mora fora da tela de documento porque a tela de pasta mostra exatamente a
 * mesma coisa, para cada documento da pasta. Duplicar isso significaria que
 * liberar uma revisão se comportaria diferente dependendo de onde se clica.
 */

import { useEffect, useState } from "react";
import {
  api,
  ErroApi,
  formatarData,
  formatarTamanho,
  type Arquivo,
  type Revisao,
  type Solicitacao,
  type Verificacao,
} from "./api";
import { Aviso, Estado } from "./componentes";
import { useSessao } from "./sessao";

/** Pede a URL assinada e baixa. Revisão não vigente exige confirmação. */
export async function baixarArquivo(
  arquivo: Arquivo,
  aoErro: (mensagem: string) => void,
  aoAvisar?: (aviso: string) => void,
) {
  try {
    const r = await api.get<{ url: string; aviso: string | null }>(
      `/arquivos/${arquivo.id}/download`,
    );
    if (r.aviso) {
      if (!window.confirm(`${r.aviso}

Baixar mesmo assim?`)) return;
      aoAvisar?.(r.aviso);
    }
    window.location.href = r.url;
  } catch (ex) {
    aoErro(ex instanceof ErroApi ? ex.message : "Não foi possível baixar.");
  }
}

/** Abre o PDF numa aba nova, no visualizador do próprio navegador.
 *
 *  A aba abre NO CLIQUE, ainda vazia, e recebe o endereço quando a API
 *  responde. Abrir só depois da resposta parece igual, mas o navegador já não
 *  considera aquilo um clique da pessoa e bloqueia como pop-up — foi o que o
 *  teste mostrou. Por isso o aviso de revisão obsoleta ou em andamento vem
 *  antes, pelo status que a tela já conhece: depois de a aba abrir, uma
 *  pergunta na tela de trás passaria despercebida. */
export function visualizarArquivo(
  arquivo: Arquivo,
  status: Revisao["status"],
  aoErro: (mensagem: string) => void,
) {
  const aviso =
    status === "obsoleto"
      ? "ATENÇÃO: esta revisão está OBSOLETA. Não use este arquivo para execução."
      : status === "reprovado"
        ? "ATENÇÃO: esta revisão foi REPROVADA na análise crítica. Não use este arquivo para execução."
        : status === "em_revisao"
          ? "Esta revisão ainda está EM REVISÃO e não foi liberada para obra."
          : null;
  if (aviso && !window.confirm(`${aviso}

Abrir mesmo assim?`)) return;

  const aba = window.open("", "_blank");
  if (!aba) {
    aoErro("O navegador bloqueou a nova aba. Permita pop-ups deste site e tente de novo.");
    return;
  }
  aba.opener = null;
  aba.document.title = arquivo.nome_original;
  aba.document.body.textContent = "Abrindo o PDF…";

  api
    .get<{ url: string }>(`/arquivos/${arquivo.id}/visualizar`)
    .then((r) => {
      aba.location.href = r.url;
    })
    .catch((ex) => {
      aba.close();
      aoErro(ex instanceof ErroApi ? ex.message : "Não foi possível abrir o arquivo.");
    });
}

export function HistoricoRevisoes({
  revisoes,
  podePublicar,
  podeCancelar,
  aoMudar,
  aoBaixar,
  solicitacoes = [],
}: {
  revisoes: Revisao[];
  /** Pedidos de revisão do documento: quem libera marca os que a revisão atende. */
  solicitacoes?: Solicitacao[];
  podePublicar: boolean;
  podeCancelar: boolean;
  aoMudar: () => Promise<void>;
  aoBaixar: (a: Arquivo) => void;
}) {
  return (
    <>
      {revisoes.map((r) => (
        <LinhaRevisao
          key={r.id}
          revisao={r}
          podePublicar={podePublicar}
          podeCancelar={podeCancelar}
          aoMudar={aoMudar}
          aoBaixar={aoBaixar}
          pedidosAutorizados={solicitacoes.filter((s) => s.status === "autorizada")}
        />
      ))}
    </>
  );
}

/** Análise crítica em andamento: qual decisão o coordenador está tomando. */
type Decisao = "liberar" | "reprovar" | null;

function LinhaRevisao({
  revisao,
  podePublicar,
  podeCancelar,
  aoMudar,
  aoBaixar,
  pedidosAutorizados,
}: {
  revisao: Revisao;
  pedidosAutorizados: Solicitacao[];
  podePublicar: boolean;
  podeCancelar: boolean;
  aoMudar: () => Promise<void>;
  aoBaixar: (a: Arquivo) => void;
}) {
  // Pedidos que esta revisão atende — marcados por quem libera. Fecham na
  // liberação; os não marcados seguem abertos.
  // Vêm marcados: a revisão nova existe por causa deles. Quem libera desmarca
  // o que ela não resolveu.
  const [atendidos, setAtendidos] = useState<number[]>(() => pedidosAutorizados.map((p) => p.id));
  // Nada se exclui (TREELE, 09/10/2026). O administrador cancela em qualquer
  // status; o coordenador, só o que está em revisão.
  const admin = useSessao().usuario?.admin ?? false;
  const [verificacao, setVerificacao] = useState<Verificacao | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [decisao, setDecisao] = useState<Decisao>(null);
  const [observacao, setObservacao] = useState("");

  const emRevisao = revisao.status === "em_revisao";
  const cancelavel =
    revisao.status !== "cancelado" && (admin || (emRevisao && podeCancelar));

  useEffect(() => {
    if (!emRevisao) return;
    api
      .get<Verificacao>(`/revisoes/${revisao.id}/verificar`)
      .then(setVerificacao)
      .catch(() => setVerificacao(null));
  }, [revisao.id, emRevisao]);

  function abrirDecisao(qual: Decisao) {
    setErro(null);
    setObservacao("");
    setDecisao(qual);
  }

  /** Liberar ou reprovar. A observação é opcional ao liberar e obrigatória ao
   *  reprovar — a API confere as duas coisas também. */
  async function decidir() {
    const texto = observacao.trim();
    if (decisao === "reprovar" && !texto) return;
    setOcupado(true);
    setErro(null);
    try {
      if (decisao === "liberar") {
        await api.post(`/revisoes/${revisao.id}/publicar`, {
          solicitacoes_atendidas: atendidos,
          observacao: texto || null,
        });
      } else {
        await api.post(`/revisoes/${revisao.id}/reprovar`, { observacao: texto });
      }
      setDecisao(null);
      await aoMudar();
    } catch (ex) {
      setErro(
        ex instanceof ErroApi
          ? ex
          : new ErroApi(0, decisao === "liberar" ? "Não foi possível liberar." : "Não foi possível reprovar."),
      );
    } finally {
      setOcupado(false);
    }
  }

  async function cancelar() {
    const avisos = [`Cancelar a revisão R${revisao.numero}? Ela fica no histórico, mas deixa de valer.`];
    if (revisao.status === "liberado_para_obra") {
      avisos.push("Ela está liberada para obra: a liberada anterior, se houver, volta a valer.");
    }
    if (!window.confirm(avisos.join("\n\n"))) return;
    setOcupado(true);
    setErro(null);
    try {
      await api.post(`/revisoes/${revisao.id}/cancelar`);
      await aoMudar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível cancelar."));
    } finally {
      setOcupado(false);
    }
  }

  async function excluirArquivo(a: Arquivo) {
    if (!window.confirm(`Excluir o arquivo ${a.nome_original} de vez?

Isto não pode ser desfeito.`)) {
      return;
    }
    setOcupado(true);
    setErro(null);
    try {
      await api.delete(`/arquivos/${a.id}`);
      await aoMudar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível excluir."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className={`revisao ${revisao.status === "obsoleto" ? "obsoleta" : ""}`}>
      <div className="revisao-topo">
        <div>
          <span className="rotulo">Revisão</span>
          <div className="numero-rev">R{revisao.numero}</div>
        </div>

        <div style={{ flex: 1, minWidth: 220 }}>
          <Estado status={revisao.status} />
          <div className="silencioso" style={{ fontSize: 12, marginTop: 6 }}>
            Enviada em {formatarData(revisao.criada_em)}
            {revisao.criada_por && ` por ${revisao.criada_por.nome}`}
            {revisao.publicada_em &&
              ` · Liberada em ${formatarData(revisao.publicada_em)}${
                revisao.publicada_por ? ` por ${revisao.publicada_por.nome}` : ""
              }`}
            {revisao.reprovada_em &&
              ` · Reprovada em ${formatarData(revisao.reprovada_em)}${
                revisao.reprovada_por ? ` por ${revisao.reprovada_por.nome}` : ""
              }`}
          </div>

          {/* Registro da análise crítica: quem liberou ou reprovou disse por quê. */}
          {revisao.observacao && (
            <div
              className={`observacao-analise ${
                revisao.status === "reprovado" ? "reprovada" : revisao.publicada_em ? "liberada" : ""
              }`}
            >
              <span className="rotulo">
                {revisao.status === "reprovado" ? "Motivo da reprovação" : "Observação da liberação"}
              </span>
              <div style={{ marginTop: 3 }}>{revisao.observacao}</div>
            </div>
          )}

          {revisao.descricao_ia && (
            <div style={{ marginTop: 10 }}>
              <span className="rotulo">O que mudou (gerado automaticamente)</span>
              <div style={{ marginTop: 3 }}>{revisao.descricao_ia}</div>
            </div>
          )}

          {/* Dito por quem abriu a revisão, no envio do primeiro arquivo. */}
          {revisao.descricao && (
            <div style={{ marginTop: 10 }}>
              <span className="rotulo">O que mudou nesta revisão</span>
              <div style={{ marginTop: 3 }}>{revisao.descricao}</div>
            </div>
          )}
        </div>

        {cancelavel && (
          <button
            className="botao perigo pequeno"
            disabled={ocupado}
            onClick={cancelar}
            title={
              emRevisao
                ? "A revisão fica no histórico, marcada como cancelada"
                : "Somente administradores cancelam fora da análise crítica"
            }
          >
            Cancelar revisão
          </button>
        )}
      </div>

      {erro && (
        <div style={{ marginTop: 12 }}>
          <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />
        </div>
      )}

      {revisao.arquivos.length > 0 && (
        <div className="arquivos">
          {revisao.arquivos.map((a) => (
            <div className="arquivo" key={a.id}>
              <div className="linha" style={{ gap: 8, minWidth: 0 }}>
                <span className="tipo">{a.tipo.toUpperCase()}</span>
                <span className="nome">{a.nome_original}</span>
                {a.status !== "disponivel" && (
                  <span className="estado estado-em_revisao">
                    {a.status === "pendente" ? "Envio incompleto" : "Falhou"}
                  </span>
                )}
              </div>
              <div className="linha">
                <span className="silencioso mono" style={{ fontSize: 11 }}>
                  {formatarTamanho(a.tamanho)}
                </span>
                {a.tipo === "pdf" && (
                  <button
                    className="botao secundario pequeno"
                    disabled={a.status !== "disponivel"}
                    onClick={() =>
                      visualizarArquivo(a, revisao.status, (m) => setErro(new ErroApi(0, m)))
                    }
                    title="Abrir numa aba nova, sem baixar"
                  >
                    Visualizar
                  </button>
                )}
                <button
                  className="botao secundario pequeno"
                  disabled={a.status !== "disponivel"}
                  onClick={() => aoBaixar(a)}
                >
                  Baixar
                </button>
                {admin && (
                  <button
                    className="botao perigo pequeno"
                    disabled={ocupado}
                    onClick={() => excluirArquivo(a)}
                  >
                    Excluir
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {emRevisao && (
        <div style={{ marginTop: 14 }}>
          {verificacao && verificacao.impedimentos.length > 0 && (
            <Aviso
              tom="atencao"
              titulo="Ainda não dá para liberar esta revisão"
              itens={verificacao.impedimentos}
            />
          )}

          {podePublicar ? (
            <>
              {pedidosAutorizados.length > 0 && decisao !== "reprovar" && (
                <fieldset className="pedidos-atendidos">
                  <legend className="rotulo">Solicitações de revisão atendidas</legend>
                  {pedidosAutorizados.map((p) => (
                    <label key={p.id} className="pedido-atendido">
                      <input
                        type="checkbox"
                        checked={atendidos.includes(p.id)}
                        onChange={() =>
                          setAtendidos((a) =>
                            a.includes(p.id) ? a.filter((x) => x !== p.id) : [...a, p.id],
                          )
                        }
                        disabled={ocupado}
                      />
                      <span>{p.descricao}</span>
                    </label>
                  ))}
                  <span className="silencioso" style={{ fontSize: 12 }}>
                    As marcadas fecham ao liberar a R{revisao.numero}. As desmarcadas continuam autorizadas.
                  </span>
                </fieldset>
              )}
              {decisao === null ? (
                <div className="linha" style={{ marginTop: 10 }}>
                  <button
                    className="botao"
                    disabled={ocupado || !verificacao?.pode_publicar}
                    onClick={() => abrirDecisao("liberar")}
                  >
                    Liberar para obra
                  </button>
                  <button
                    className="botao secundario"
                    disabled={ocupado}
                    onClick={() => abrirDecisao("reprovar")}
                  >
                    Reprovar
                  </button>
                </div>
              ) : (
                <div className={`analise ${decisao}`}>
                  <label className="campo" style={{ display: "block" }}>
                    <span className="rotulo">
                      Observação{" "}
                      {decisao === "liberar" ? "(opcional)" : "(obrigatória — vai para quem enviou)"}
                    </span>
                    <textarea
                      value={observacao}
                      onChange={(e) => setObservacao(e.target.value)}
                      maxLength={4000}
                      autoFocus
                      placeholder={
                        decisao === "liberar"
                          ? "Algo que a obra ou a equipe deve saber sobre esta liberação."
                          : "O que precisa ser corrigido na próxima revisão."
                      }
                      disabled={ocupado}
                    />
                  </label>
                  <div className="linha" style={{ marginTop: 10 }}>
                    <button
                      className={decisao === "liberar" ? "botao" : "botao perigo"}
                      disabled={ocupado || (decisao === "reprovar" && !observacao.trim())}
                      onClick={decidir}
                    >
                      {decisao === "liberar"
                        ? ocupado
                          ? "Liberando…"
                          : `Liberar R${revisao.numero} para obra`
                        : ocupado
                          ? "Reprovando…"
                          : `Reprovar R${revisao.numero}`}
                    </button>
                    <button
                      className="botao secundario pequeno"
                      disabled={ocupado}
                      onClick={() => setDecisao(null)}
                    >
                      Voltar
                    </button>
                  </div>
                  {decisao === "reprovar" && (
                    <p className="silencioso" style={{ fontSize: 12, margin: "8px 0 0" }}>
                      A R{revisao.numero} fica no histórico como reprovada. Quem a enviou recebe a
                      observação por e-mail, e a correção vem numa revisão nova.
                    </p>
                  )}
                </div>
              )}
            </>
          ) : (
            <p className="silencioso" style={{ fontSize: 12, margin: 0 }}>
              Esta revisão está em análise crítica pelo coordenador da obra.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
