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
  type Verificacao,
} from "./api";
import { Aviso, Estado } from "./componentes";

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

export function HistoricoRevisoes({
  revisoes,
  podePublicar,
  podeCancelar,
  aoMudar,
  aoBaixar,
}: {
  revisoes: Revisao[];
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
        />
      ))}
    </>
  );
}

function LinhaRevisao({
  revisao,
  podePublicar,
  podeCancelar,
  aoMudar,
  aoBaixar,
}: {
  revisao: Revisao;
  podePublicar: boolean;
  podeCancelar: boolean;
  aoMudar: () => Promise<void>;
  aoBaixar: (a: Arquivo) => void;
}) {
  const [verificacao, setVerificacao] = useState<Verificacao | null>(null);
  const [descricao, setDescricao] = useState(revisao.descricao ?? "");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);

  const emRevisao = revisao.status === "em_revisao";

  useEffect(() => {
    if (!emRevisao) return;
    api
      .get<Verificacao>(`/revisoes/${revisao.id}/verificar`)
      .then(setVerificacao)
      .catch(() => setVerificacao(null));
  }, [revisao.id, emRevisao]);

  async function publicar() {
    setOcupado(true);
    setErro(null);
    try {
      await api.post(`/revisoes/${revisao.id}/publicar`, { descricao: descricao.trim() || null });
      await aoMudar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível liberar."));
    } finally {
      setOcupado(false);
    }
  }

  async function cancelar() {
    if (!window.confirm(`Cancelar a revisão R${revisao.numero}? Ela deixa de valer.`)) return;
    setOcupado(true);
    try {
      await api.post(`/revisoes/${revisao.id}/cancelar`);
      await aoMudar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível cancelar."));
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
          </div>

          {revisao.descricao_ia && (
            <div style={{ marginTop: 10 }}>
              <span className="rotulo">O que mudou (gerado automaticamente)</span>
              <div style={{ marginTop: 3 }}>{revisao.descricao_ia}</div>
            </div>
          )}

          {revisao.descricao && !emRevisao && (
            <div style={{ marginTop: 10 }}>
              <span className="rotulo">Descrição</span>
              <div style={{ marginTop: 3 }}>{revisao.descricao}</div>
            </div>
          )}
        </div>
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
                <button
                  className="botao secundario pequeno"
                  disabled={a.status !== "disponivel"}
                  onClick={() => aoBaixar(a)}
                >
                  Baixar
                </button>
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
              <label className="campo">
                <span className="rotulo">O que mudou nesta revisão</span>
                <textarea
                  value={descricao}
                  onChange={(e) => setDescricao(e.target.value)}
                  placeholder="Ex.: Ajuste de armadura da viga V12 e revisão das cotas do eixo 4."
                />
              </label>
              <div className="linha" style={{ marginTop: 10 }}>
                <button
                  className="botao"
                  disabled={ocupado || !verificacao?.pode_publicar}
                  onClick={publicar}
                >
                  {ocupado ? "Liberando…" : "Liberar para obra"}
                </button>
                {podeCancelar && (
                  <button className="botao perigo pequeno" disabled={ocupado} onClick={cancelar}>
                    Cancelar revisão
                  </button>
                )}
              </div>
            </>
          ) : (
            <p className="silencioso" style={{ fontSize: 12, margin: 0 }}>
              Esta revisão aguarda liberação do coordenador da obra.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
