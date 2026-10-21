/** Chat do acervo (Fase 2): perguntas em português, respostas a partir das
 *  consultas ao catálogo — com as permissões de quem pergunta. A conversa vive
 *  só nesta tela: nada fica guardado no servidor. */

import { Fragment, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ErroApi, lerToken } from "./api";
import { useSessao } from "./sessao";

interface Turno {
  papel: "usuario" | "assistente";
  texto: string;
  /** O que o assistente fez para chegar na resposta (só para mostrar). */
  etapas?: string[];
}

type Evento = { tipo: "etapa" | "resposta" | "erro"; texto: string };

/** Pergunta pela rota com etapas: cada linha da resposta é um evento, e as
 *  etapas aparecem enquanto o assistente trabalha (TREELE, 21/10/2026). */
async function perguntarComEtapas(
  corpo: { mensagens: { papel: string; texto: string }[]; obra_id: number | null },
  aoEvento: (e: Evento) => void,
): Promise<void> {
  const r = await fetch(`${api.base}/chat/fluxo`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${lerToken()}` },
    body: JSON.stringify(corpo),
  });
  if (!r.ok || !r.body) {
    let mensagem = "Não foi possível falar com o assistente.";
    try {
      const d = await r.json();
      if (typeof d.detail === "string") mensagem = d.detail;
    } catch {
      /* corpo sem JSON: fica a mensagem geral */
    }
    throw new ErroApi(r.status, mensagem);
  }
  const leitor = r.body.getReader();
  const decodificador = new TextDecoder();
  let resto = "";
  for (;;) {
    const { value, done } = await leitor.read();
    resto += decodificador.decode(value ?? new Uint8Array(), { stream: !done });
    const linhas = resto.split("\n");
    resto = linhas.pop() ?? "";
    for (const linha of linhas) if (linha.trim()) aoEvento(JSON.parse(linha) as Evento);
    if (done) break;
  }
  if (resto.trim()) aoEvento(JSON.parse(resto) as Evento);
}

function Etapas({ etapas }: { etapas: string[] }) {
  if (!etapas.length) return null;
  return (
    <details className="assistente-etapas">
      <summary>
        Ver etapas ({etapas.length})
      </summary>
      <ol>
        {etapas.map((e, i) => (
          <li key={i}>{e}</li>
        ))}
      </ol>
    </details>
  );
}

const SUGESTOES_EQUIPE = [
  "O que foi liberado para obra nesta semana?",
  "O que dizem as notas gerais da planta baixa do térreo?",
  "Quais documentos desta obra ainda estão em revisão?",
  "Há solicitações de revisão aguardando autorização?",
];
const SUGESTOES_OBRA = [
  "O que foi liberado para obra nesta semana?",
  "Qual a revisão atual da planta baixa do térreo?",
  "O que dizem as notas gerais da planta baixa do térreo?",
  "Quais projetos de estrutura já estão liberados?",
];

/* ------------------------------------------------- markdown, o mínimo e seguro */

/** Negrito e links internos. Link só para dentro do sistema ("/..."): um
 *  endereço de fora que o modelo escrevesse vira texto, nunca link. */
function trecho(texto: string, chave: string): ReactNode[] {
  const saida: ReactNode[] = [];
  const padrao = /\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*/g;
  let ultimo = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = padrao.exec(texto))) {
    if (m.index > ultimo) saida.push(texto.slice(ultimo, m.index));
    if (m[1] !== undefined) {
      const destino = m[2];
      saida.push(
        destino.startsWith("/") && !destino.startsWith("//") ? (
          <Link key={`${chave}-${i++}`} to={destino}>
            {m[1]}
          </Link>
        ) : (
          m[1]
        ),
      );
    } else {
      saida.push(<strong key={`${chave}-${i++}`}>{m[3]}</strong>);
    }
    ultimo = m.index + m[0].length;
  }
  if (ultimo < texto.length) saida.push(texto.slice(ultimo));
  return saida;
}

function Markdown({ texto }: { texto: string }) {
  const blocos: ReactNode[] = [];
  let lista: ReactNode[] = [];
  const fecharLista = () => {
    if (lista.length) {
      blocos.push(<ul key={`l${blocos.length}`}>{lista}</ul>);
      lista = [];
    }
  };
  texto.split("\n").forEach((linha, n) => {
    const item = linha.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (item) {
      lista.push(<li key={n}>{trecho(item[1], `i${n}`)}</li>);
      return;
    }
    fecharLista();
    if (linha.trim()) {
      const titulo = linha.match(/^#{1,4}\s+(.*)$/);
      blocos.push(
        <p key={n} className={titulo ? "titulo-resposta" : undefined}>
          {trecho(titulo ? titulo[1] : linha, `p${n}`)}
        </p>,
      );
    }
  });
  fecharLista();
  return <Fragment>{blocos}</Fragment>;
}

/* ------------------------------------------------------------------ o chat */

export default function Assistente({ obraId }: { obraId: number | null }) {
  const { usuario, obras } = useSessao();
  const [ligado, setLigado] = useState(false);
  const [fornecedor, setFornecedor] = useState<string | null>(null);
  const [aberto, setAberto] = useState(false);
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [texto, setTexto] = useState("");
  const [pensando, setPensando] = useState(false);
  const [etapas, setEtapas] = useState<string[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const fim = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api
      .get<{ ligado: boolean; fornecedor: string | null }>("/chat/estado")
      .then((r) => {
        setLigado(r.ligado);
        setFornecedor(r.fornecedor);
      })
      .catch(() => setLigado(false));
  }, []);

  useEffect(() => {
    fim.current?.scrollIntoView({ block: "end" });
  }, [turnos, pensando, aberto, etapas]);

  useEffect(() => {
    if (aberto) campo.current?.focus();
  }, [aberto]);

  if (!ligado) return null;

  const papelNaObra = obras.find((o) => o.id === obraId)?.papel;
  const sugestoes =
    usuario?.comercial || papelNaObra === "obra" ? SUGESTOES_OBRA : SUGESTOES_EQUIPE;

  async function perguntar(pergunta: string) {
    const limpa = pergunta.trim();
    if (!limpa || pensando) return;
    const conversa: Turno[] = [...turnos, { papel: "usuario", texto: limpa }];
    setTurnos(conversa);
    setTexto("");
    setErro(null);
    setPensando(true);
    setEtapas([]);
    const feitas: string[] = [];
    let resposta: string | null = null;
    let falha: string | null = null;
    try {
      await perguntarComEtapas(
        // Para o servidor vai só a conversa; as etapas ficam na tela.
        { mensagens: conversa.map(({ papel, texto }) => ({ papel, texto })), obra_id: obraId },
        (e) => {
          if (e.tipo === "etapa") {
            feitas.push(e.texto);
            setEtapas([...feitas]);
          } else if (e.tipo === "resposta") resposta = e.texto;
          else falha = e.texto;
        },
      );
      if (resposta === null && falha === null) falha = "O assistente não terminou de responder. Tente de novo.";
    } catch (ex) {
      falha = ex instanceof ErroApi ? ex.message : "Não foi possível falar com o assistente.";
    }
    if (resposta !== null) {
      setTurnos([...conversa, { papel: "assistente", texto: resposta, etapas: feitas }]);
    } else {
      setErro(falha);
      // A pergunta volta para o campo: dá para tentar de novo sem redigitar.
      setTurnos(turnos);
      setTexto(limpa);
    }
    setPensando(false);
    setEtapas([]);
  }

  function enviar(e: FormEvent) {
    e.preventDefault();
    void perguntar(texto);
  }

  return (
    <>
      {!aberto && (
        <button className="assistente-botao" onClick={() => setAberto(true)}>
          <span className="assistente-icone" aria-hidden="true">
            ✦
          </span>
          Perguntar ao acervo
        </button>
      )}

      {aberto && (
        <aside className="assistente-painel" aria-label="Assistente do acervo">
          <header className="assistente-topo">
            <div>
              <strong>Assistente do acervo</strong>
              <span>Pergunte sobre documentos, revisões e liberações</span>
            </div>
            <div className="linha" style={{ gap: 6 }}>
              {turnos.length > 0 && (
                <button
                  className="botao secundario pequeno"
                  onClick={() => {
                    setTurnos([]);
                    setErro(null);
                  }}
                  disabled={pensando}
                >
                  Nova conversa
                </button>
              )}
              <button
                className="assistente-fechar"
                onClick={() => setAberto(false)}
                aria-label="Fechar o assistente"
              >
                ×
              </button>
            </div>
          </header>

          <div className="assistente-conversa">
            {turnos.length === 0 && (
              <div className="assistente-vazio">
                <p>Algumas ideias:</p>
                {sugestoes.map((s) => (
                  <button key={s} className="assistente-sugestao" onClick={() => perguntar(s)}>
                    {s}
                  </button>
                ))}
              </div>
            )}
            {turnos.map((t, i) => (
              <div key={i} className={`assistente-msg ${t.papel}`}>
                {t.papel === "assistente" ? (
                  <>
                    {t.etapas && <Etapas etapas={t.etapas} />}
                    <Markdown texto={t.texto} />
                  </>
                ) : (
                  t.texto
                )}
              </div>
            ))}
            {pensando && (
              <div className="assistente-msg assistente pensando" aria-live="polite">
                {etapas.length === 0 ? (
                  "Pensando…"
                ) : (
                  <ol className="assistente-etapas-vivas">
                    {etapas.map((e, i) => (
                      <li key={i} className={i === etapas.length - 1 ? "atual" : undefined}>
                        {e}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}
            {erro && <div className="assistente-erro">{erro}</div>}
            <div ref={fim} />
          </div>

          <form className="assistente-entrada" onSubmit={enviar}>
            <textarea
              ref={campo}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => {
                // Enter envia; Shift+Enter quebra a linha.
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void perguntar(texto);
                }
              }}
              placeholder="Ex.: qual a revisão atual da fachada?"
              rows={2}
              maxLength={2000}
              disabled={pensando}
            />
            <button className="botao" disabled={pensando || !texto.trim()}>
              Enviar
            </button>
          </form>
          <p className="assistente-nota">
            Respostas geradas por IA{fornecedor ? ` (${fornecedor})` : ""} a partir do acervo e, quando preciso, do
            PDF da prancha. Confira no documento antes de executar.
          </p>
        </aside>
      )}
    </>
  );
}
