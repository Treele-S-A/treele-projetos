/** Solicitação de revisão: a obra pede, o coordenador autoriza, o projeto atende.
 *
 * O pedido é sobre o projeto liberado. O coordenador autoriza ou recusa (com
 * motivo) — e também autoriza direto, sem pedido. Só com revisão autorizada o
 * documento aceita revisão nova; o pedido fecha quando quem libera a revisão
 * nova o marca como atendido. A descrição é obrigatória; fotos e PDFs, não.
 */

import { useRef, useState, type FormEvent } from "react";
import { api, ErroApi, formatarData, formatarTamanho, type Anexo, type Solicitacao } from "./api";
import { Aviso } from "./componentes";

const DESCRICAO_MIN = 10;
const MOTIVO_MIN = 10;
const ANEXO_MAX_MB = 25;
const ACEITOS = ".pdf,.jpg,.jpeg,.png,.webp";

/** As marcas ao lado do status: o projeto continua liberado, mas há pedido
 *  esperando o coordenador, ou revisão já autorizada a caminho. */
export function MarcaSolicitada({
  quantidade,
  autorizadas = 0,
}: {
  quantidade: number;
  autorizadas?: number;
}) {
  return (
    <>
      {quantidade > 0 && (
        <span className="marca-solicitada" title="Pedido de revisão esperando o coordenador">
          Revisão solicitada{quantidade > 1 ? ` (${quantidade})` : ""}
        </span>
      )}
      {autorizadas > 0 && (
        <span
          className="marca-solicitada autorizada"
          title="Revisão autorizada: a nova vai substituir esta"
        >
          Revisão autorizada{autorizadas > 1 ? ` (${autorizadas})` : ""}
        </span>
      )}
    </>
  );
}

/** Abre o anexo numa aba nova — a aba abre no clique, como no PDF de projeto. */
function abrirAnexo(anexo: Anexo, aoErro: (m: string) => void) {
  const aba = window.open("", "_blank");
  if (!aba) {
    aoErro("O navegador bloqueou a nova aba. Permita pop-ups deste site e tente de novo.");
    return;
  }
  aba.opener = null;
  aba.document.title = anexo.nome_original;
  aba.document.body.textContent = "Abrindo o anexo…";
  api
    .get<{ url: string }>(`/anexos/${anexo.id}/visualizar`)
    .then((r) => {
      aba.location.href = r.url;
    })
    .catch((ex) => {
      aba.close();
      aoErro(ex instanceof ErroApi ? ex.message : "Não foi possível abrir o anexo.");
    });
}

async function subirAnexo(solicitacaoId: number, arquivo: File) {
  const inicio = await api.post<{
    anexo_id: number;
    url: string;
    metodo: string;
    headers: Record<string, string>;
  }>(`/solicitacoes/${solicitacaoId}/anexos`, {
    nome_arquivo: arquivo.name,
    tamanho: arquivo.size,
  });
  const resposta = await fetch(inicio.url, {
    method: inicio.metodo,
    headers: inicio.headers,
    body: arquivo,
  });
  if (!resposta.ok) throw new Error(`O armazenamento recusou ${arquivo.name}.`);
  await api.post(`/anexos/${inicio.anexo_id}/confirmar`);
}

// Ordem na tela: o que pede decisão primeiro, o encerrado por último.
const ORDEM: Record<Solicitacao["status"], number> = {
  aberta: 0,
  autorizada: 1,
  atendida: 2,
  recusada: 3,
};

export function SolicitacoesDoDocumento({
  documentoId,
  solicitacoes,
  podeSolicitar,
  podeAutorizar,
  temLiberada,
  aoMudar,
}: {
  documentoId: number;
  solicitacoes: Solicitacao[];
  podeSolicitar: boolean;
  /** Coordenador: autoriza, recusa, e o pedido dele já nasce autorizado. */
  podeAutorizar: boolean;
  temLiberada: boolean;
  aoMudar: () => Promise<void>;
}) {
  const [abrindo, setAbrindo] = useState(false);
  const [descricao, setDescricao] = useState("");
  const [anexos, setAnexos] = useState<File[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const entrada = useRef<HTMLInputElement>(null);

  const ordenadas = [...solicitacoes].sort((a, b) => ORDEM[a.status] - ORDEM[b.status]);
  const pode = (podeSolicitar || podeAutorizar) && temLiberada;
  if (solicitacoes.length === 0 && !pode) return null;

  const verbo = podeAutorizar ? "Autorizar revisão" : "Solicitar revisão";

  function escolher(arquivos: File[]) {
    const grandes = arquivos.filter((a) => a.size > ANEXO_MAX_MB * 1024 * 1024);
    setErro(
      grandes.length
        ? `Cada anexo pode ter até ${ANEXO_MAX_MB} MB: ${grandes.map((a) => a.name).join(", ")}.`
        : null,
    );
    setAnexos((atuais) => [...atuais, ...arquivos.filter((a) => !grandes.includes(a))]);
  }

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setOk(null);
    setEnviando(true);
    try {
      const criada = await api.post<Solicitacao>(`/documentos/${documentoId}/solicitacoes`, {
        descricao: descricao.trim(),
      });
      // O pedido já existe; um anexo que falhe não o desfaz — avisa e segue.
      const falharam: string[] = [];
      for (const arquivo of anexos) {
        try {
          await subirAnexo(criada.id, arquivo);
        } catch {
          falharam.push(arquivo.name);
        }
      }
      setDescricao("");
      setAnexos([]);
      setAbrindo(false);
      await aoMudar();
      if (falharam.length) {
        setErro(`Registrado, mas não foi possível anexar: ${falharam.join(", ")}.`);
      } else if (criada.status === "autorizada") {
        setOk("Revisão autorizada. O projetista da última revisão foi avisado.");
      } else {
        setOk("Solicitação registrada. O coordenador vai autorizar ou recusar.");
      }
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível registrar a solicitação.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="folha">
      <div className="folha-titulo">
        <strong>Solicitações de revisão</strong>
        {pode && !abrindo && (
          <button className="botao pequeno" onClick={() => setAbrindo(true)}>
            {verbo}
          </button>
        )}
      </div>

      <div className="folha-corpo">
        {erro && <Aviso tom="erro">{erro}</Aviso>}
        {ok && <Aviso tom="ok">{ok}</Aviso>}

        {abrindo && (
          <form className="form-solicitacao" onSubmit={enviar}>
            <label className="campo">
              <span className="rotulo">O que deve mudar no projeto</span>
              <textarea
                value={descricao}
                onChange={(e) => setDescricao(e.target.value)}
                placeholder="Ex.: O shaft do banheiro bate na viga V12 — compatibilizar a posição."
                maxLength={4000}
                rows={4}
                autoFocus
                required
              />
            </label>
            {podeAutorizar && (
              <p className="silencioso" style={{ margin: "6px 0 0", fontSize: 12 }}>
                Como coordenador, a revisão já sai autorizada e o projetista da última revisão
                é avisado.
              </p>
            )}

            <div className="linha" style={{ marginTop: 10 }}>
              <button
                type="button"
                className="botao secundario pequeno"
                onClick={() => entrada.current?.click()}
                disabled={enviando}
              >
                Anexar fotos ou PDF
              </button>
              <span className="silencioso" style={{ fontSize: 12 }}>
                Opcional · JPG, PNG, WebP ou PDF · até {ANEXO_MAX_MB} MB cada
              </span>
              <input
                ref={entrada}
                type="file"
                multiple
                accept={ACEITOS}
                hidden
                onChange={(e) => {
                  escolher(Array.from(e.target.files ?? []));
                  e.target.value = "";
                }}
              />
            </div>

            {anexos.length > 0 && (
              <ul className="anexos-escolhidos">
                {anexos.map((a, i) => (
                  <li key={`${a.name}-${i}`}>
                    <span className="mono">{a.name}</span>
                    <span className="silencioso">{formatarTamanho(a.size)}</span>
                    <button
                      type="button"
                      className="botao secundario pequeno"
                      onClick={() => setAnexos((atuais) => atuais.filter((_, j) => j !== i))}
                      disabled={enviando}
                    >
                      Tirar
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="linha" style={{ marginTop: 14 }}>
              <button
                className="botao"
                disabled={enviando || descricao.trim().length < DESCRICAO_MIN}
              >
                {enviando ? "Enviando…" : podeAutorizar ? "Autorizar revisão" : "Enviar solicitação"}
              </button>
              <button
                type="button"
                className="botao secundario"
                onClick={() => {
                  setAbrindo(false);
                  setDescricao("");
                  setAnexos([]);
                }}
                disabled={enviando}
              >
                Cancelar
              </button>
              {descricao.trim().length > 0 && descricao.trim().length < DESCRICAO_MIN && (
                <span className="silencioso" style={{ fontSize: 12 }}>
                  Descreva com pelo menos {DESCRICAO_MIN} caracteres.
                </span>
              )}
            </div>
          </form>
        )}

        {ordenadas.map((s) => (
          <ItemSolicitacao
            key={s.id}
            solicitacao={s}
            podeDecidir={podeAutorizar}
            aoErro={setErro}
            aoOk={setOk}
            aoMudar={aoMudar}
          />
        ))}

        {solicitacoes.length === 0 && !abrindo && (
          <p className="silencioso" style={{ margin: 0, fontSize: 13 }}>
            {podeAutorizar
              ? "Nenhuma solicitação. Para abrir uma revisão nova deste documento, autorize aqui."
              : "Nenhuma solicitação. Se algo do projeto liberado precisa mudar, peça a revisão aqui."}
          </p>
        )}
      </div>
    </div>
  );
}

const ROTULO: Record<Solicitacao["status"], string> = {
  aberta: "Aguardando autorização",
  autorizada: "Autorizada",
  atendida: "Atendida",
  recusada: "Recusada",
};

const ESTILO: Record<Solicitacao["status"], string> = {
  aberta: "estado-em_revisao",
  autorizada: "estado-autorizada",
  atendida: "estado-liberado_para_obra",
  recusada: "estado-cancelado",
};

function ItemSolicitacao({
  solicitacao: s,
  podeDecidir,
  aoErro,
  aoOk,
  aoMudar,
}: {
  solicitacao: Solicitacao;
  podeDecidir: boolean;
  aoErro: (m: string | null) => void;
  aoOk: (m: string | null) => void;
  aoMudar: () => Promise<void>;
}) {
  const [recusando, setRecusando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function decidir(acao: "autorizar" | "recusar") {
    aoErro(null);
    aoOk(null);
    setOcupado(true);
    try {
      await api.post(
        `/solicitacoes/${s.id}/${acao}`,
        acao === "recusar" ? { motivo: motivo.trim() } : undefined,
      );
      setRecusando(false);
      setMotivo("");
      await aoMudar();
      aoOk(
        acao === "autorizar"
          ? "Revisão autorizada. O projetista da última revisão foi avisado."
          : "Solicitação recusada. Quem pediu foi avisado, com o motivo.",
      );
    } catch (ex) {
      aoErro(ex instanceof ErroApi ? ex.message : "Não foi possível registrar a decisão.");
    } finally {
      setOcupado(false);
    }
  }

  const encerrada = s.status === "atendida" || s.status === "recusada";
  return (
    <div className={`solicitacao ${encerrada ? "atendida" : "aberta"}`}>
      <div className="linha" style={{ gap: 8 }}>
        <span className={`estado ${ESTILO[s.status]}`}>{ROTULO[s.status]}</span>
        <span className="silencioso" style={{ fontSize: 12 }}>
          {s.criada_por ? `${s.criada_por.nome} · ` : ""}
          {formatarData(s.criada_em)}
          {s.revisao_numero ? ` · sobre a R${s.revisao_numero}` : ""}
          {(s.status === "autorizada" || s.status === "recusada") &&
            s.decidida_por &&
            s.decidida_por.id !== s.criada_por?.id &&
            ` · ${s.status === "autorizada" ? "autorizada" : "recusada"} por ${s.decidida_por.nome} em ${formatarData(s.decidida_em)}`}
          {s.status === "atendida" &&
            ` · atendida${s.atendida_por_numero ? ` pela R${s.atendida_por_numero}` : ""} em ${formatarData(s.atendida_em)}`}
        </span>
      </div>
      <p className="descricao-solicitacao">{s.descricao}</p>
      {s.status === "recusada" && s.motivo_recusa && (
        <p className="descricao-solicitacao motivo-recusa">
          <strong>Motivo da recusa:</strong> {s.motivo_recusa}
        </p>
      )}
      {s.anexos.length > 0 && (
        <div className="linha" style={{ gap: 6 }}>
          {s.anexos.map((a) => (
            <button
              key={a.id}
              className="botao secundario pequeno"
              onClick={() => abrirAnexo(a, aoErro)}
              title="Abrir numa aba nova"
            >
              {a.content_type === "application/pdf" ? "PDF" : "Foto"} · {a.nome_original}
            </button>
          ))}
        </div>
      )}

      {podeDecidir && s.status === "aberta" && !recusando && (
        <div className="linha" style={{ gap: 8, marginTop: 10 }}>
          <button className="botao pequeno" onClick={() => decidir("autorizar")} disabled={ocupado}>
            {ocupado ? "Autorizando…" : "Autorizar revisão"}
          </button>
          <button
            className="botao secundario pequeno"
            onClick={() => setRecusando(true)}
            disabled={ocupado}
          >
            Recusar
          </button>
        </div>
      )}
      {recusando && (
        <div style={{ marginTop: 10 }}>
          <label className="campo">
            <span className="rotulo">Por que a revisão não será feita</span>
            <textarea
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Ex.: A posição segue o projeto aprovado na prefeitura."
              maxLength={4000}
              rows={3}
              autoFocus
            />
          </label>
          <div className="linha" style={{ gap: 8, marginTop: 8 }}>
            <button
              className="botao pequeno"
              onClick={() => decidir("recusar")}
              disabled={ocupado || motivo.trim().length < MOTIVO_MIN}
            >
              {ocupado ? "Recusando…" : "Recusar solicitação"}
            </button>
            <button
              className="botao secundario pequeno"
              onClick={() => {
                setRecusando(false);
                setMotivo("");
              }}
              disabled={ocupado}
            >
              Voltar
            </button>
            {motivo.trim().length > 0 && motivo.trim().length < MOTIVO_MIN && (
              <span className="silencioso" style={{ fontSize: 12 }}>
                Explique com pelo menos {MOTIVO_MIN} caracteres — é o que quem pediu vai ler.
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
