/** Solicitação de revisão: a obra (ou o coordenador) pede, o projeto atende.
 *
 * O pedido é sobre o projeto liberado e fecha sozinho quando a revisão nova é
 * liberada para obra. A descrição é obrigatória; fotos e PDFs marcados, não.
 */

import { useRef, useState, type FormEvent } from "react";
import { api, ErroApi, formatarData, formatarTamanho, type Anexo, type Solicitacao } from "./api";
import { Aviso } from "./componentes";

const DESCRICAO_MIN = 10;
const ANEXO_MAX_MB = 25;
const ACEITOS = ".pdf,.jpg,.jpeg,.png,.webp";

/** A marca ao lado do status: o projeto continua liberado, mas há pedido aberto. */
export function MarcaSolicitada({ quantidade }: { quantidade: number }) {
  if (quantidade <= 0) return null;
  return (
    <span className="marca-solicitada" title="Há pedido de revisão em aberto">
      Revisão solicitada{quantidade > 1 ? ` (${quantidade})` : ""}
    </span>
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

export function SolicitacoesDoDocumento({
  documentoId,
  solicitacoes,
  podeSolicitar,
  temLiberada,
  aoMudar,
}: {
  documentoId: number;
  solicitacoes: Solicitacao[];
  podeSolicitar: boolean;
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

  const abertas = solicitacoes.filter((s) => s.status === "aberta");
  const atendidas = solicitacoes.filter((s) => s.status === "atendida");
  if (solicitacoes.length === 0 && !(podeSolicitar && temLiberada)) return null;

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
        setErro(`Solicitação registrada, mas não foi possível anexar: ${falharam.join(", ")}.`);
      } else {
        setOk("Solicitação registrada. A equipe de projetos vai vê-la ao lado do status.");
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
        {podeSolicitar && temLiberada && !abrindo && (
          <button className="botao pequeno" onClick={() => setAbrindo(true)}>
            Solicitar revisão
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
                {enviando ? "Enviando…" : "Enviar solicitação"}
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

        {abertas.map((s) => (
          <ItemSolicitacao key={s.id} solicitacao={s} aoErro={setErro} />
        ))}
        {atendidas.map((s) => (
          <ItemSolicitacao key={s.id} solicitacao={s} aoErro={setErro} />
        ))}

        {solicitacoes.length === 0 && !abrindo && (
          <p className="silencioso" style={{ margin: 0, fontSize: 13 }}>
            Nenhuma solicitação. Se algo do projeto liberado precisa mudar, peça a revisão aqui.
          </p>
        )}
      </div>
    </div>
  );
}

function ItemSolicitacao({
  solicitacao: s,
  aoErro,
}: {
  solicitacao: Solicitacao;
  aoErro: (m: string) => void;
}) {
  const aberta = s.status === "aberta";
  return (
    <div className={`solicitacao ${aberta ? "aberta" : "atendida"}`}>
      <div className="linha" style={{ gap: 8 }}>
        <span className={`estado ${aberta ? "estado-em_revisao" : "estado-liberado_para_obra"}`}>
          {aberta ? "Aberta" : "Atendida"}
        </span>
        <span className="silencioso" style={{ fontSize: 12 }}>
          {s.criada_por ? `${s.criada_por.nome} · ` : ""}
          {formatarData(s.criada_em)}
          {s.revisao_numero ? ` · sobre a R${s.revisao_numero}` : ""}
          {!aberta &&
            ` · atendida${s.atendida_por_numero ? ` pela R${s.atendida_por_numero}` : ""} em ${formatarData(s.atendida_em)}`}
        </span>
      </div>
      <p className="descricao-solicitacao">{s.descricao}</p>
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
    </div>
  );
}
