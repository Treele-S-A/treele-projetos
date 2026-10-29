/** Fornecedores de projetos — PRO-FL-002 (TREELE, 29/10/2026).
 *
 *  A planilha virou uma base: a tabela dos projetistas, com a qualificação
 *  documental (registro no conselho + portfólio) e o desempenho. Clicar num
 *  fornecedor abre o painel com o histórico de avaliações e o cadastro.
 *
 *  A avaliação de desempenho (procedimento 5.3) deixou de ser quatro colunas
 *  de número: cada critério é uma régua de 1 a 10 com o que cada faixa quer
 *  dizer, a média aparece num mostrador com a linha do 6, e o resultado —
 *  continua qualificado ou não — se vê enquanto se avalia. Abaixo de 6, o
 *  motivo da desqualificação passa a ser pedido. */

import { useEffect, useMemo, useState, type CSSProperties, type FormEvent } from "react";
import { api, ErroApi, formatarData } from "../api";
import { Aviso, Carregando, Vazio } from "../componentes";
import { useSessao } from "../sessao";

interface Avaliacao {
  id: number;
  obra_id: number | null;
  empreendimento: string;
  escopo: string | null;
  data: string;
  qualidade: number;
  documentacao: number;
  prazo: number;
  atendimento: number;
  media: number;
  continua_qualificado: boolean;
  motivo: string | null;
  comentario: string | null;
  avaliado_por: string | null;
}

interface Fornecedor {
  id: number;
  cod_sienge: string | null;
  razao_social: string;
  nome_fantasia: string | null;
  cnpj: string | null;
  contato: string | null;
  email: string | null;
  telefone: string | null;
  observacoes: string | null;
  registro_conselho: "SIM" | "NAO" | "NA" | null;
  portfolio: boolean | null;
  escopos: string[];
  padroes: string[];
  ativo: boolean;
  qualificacao: "qualificado" | "desqualificado" | null;
  avaliado: boolean;
  continua_qualificado: boolean | null;
  situacao: "qualificado" | "desqualificado" | "pendente";
  ultima_avaliacao: Avaliacao | null;
  total_avaliacoes: number;
  media_geral: number | null;
  avaliacoes?: Avaliacao[];
}

interface Opcoes {
  escopos: { codigo: string; nome: string }[];
  padroes: { codigo: string; nome: string }[];
  nota_minima: number;
}

type Criterio = "qualidade" | "documentacao" | "prazo" | "atendimento";

const CRITERIOS: { chave: Criterio; nome: string; curto: string; dica: string }[] = [
  {
    chave: "qualidade",
    nome: "Qualidade do serviço",
    curto: "Qualidade",
    dica: "Solução técnica, clareza das pranchas, compatibilização com as outras disciplinas.",
  },
  {
    chave: "documentacao",
    nome: "Conformidade da documentação",
    curto: "Documentação",
    dica: "Nomenclatura, carimbo, formatos e arquivos completos no padrão Treèle.",
  },
  {
    chave: "prazo",
    nome: "Prazo de entrega",
    curto: "Prazo",
    dica: "Atendimento ao cronograma contratado, entregas e revisões no tempo combinado.",
  },
  {
    chave: "atendimento",
    nome: "Atendimento e comunicação",
    curto: "Atendimento",
    dica: "Retorno às solicitações, presença nas reuniões e clareza na comunicação.",
  },
];

const ROTULO_SITUACAO = { qualificado: "Qualificado", desqualificado: "Desqualificado", pendente: "Pendente" };

function faixa(nota: number): { nome: string; cor: string } {
  if (nota < 4) return { nome: "Insatisfatório", cor: "#b3261e" };
  if (nota < 6) return { nome: "Regular", cor: "#c26a00" };
  if (nota < 8) return { nome: "Bom", cor: "#6a8f1a" };
  if (nota < 10) return { nome: "Muito bom", cor: "#3f7a24" };
  return { nome: "Excelente", cor: "#2c6a2e" };
}

function nota1(n: number) {
  return n.toFixed(1).replace(".", ",");
}

/** Mostrador da média: o anel enche até a nota, com o traço do mínimo. */
function Mostrador({ media, minima, tamanho = 56 }: { media: number | null; minima: number; tamanho?: number }) {
  const r = tamanho / 2 - 5;
  const volta = 2 * Math.PI * r;
  const cor = media === null ? "var(--traco-medio)" : faixa(media).cor;
  const angMin = (minima / 10) * 2 * Math.PI - Math.PI / 2;
  const c = tamanho / 2;
  return (
    <svg className="mostrador" width={tamanho} height={tamanho} viewBox={`0 0 ${tamanho} ${tamanho}`} role="img"
      aria-label={media === null ? "Sem avaliação" : `Média ${nota1(media)} de 10`}>
      <circle cx={c} cy={c} r={r} fill="none" stroke="var(--traco-fino)" strokeWidth={6} />
      {media !== null && (
        <circle cx={c} cy={c} r={r} fill="none" stroke={cor} strokeWidth={6} strokeLinecap="round"
          strokeDasharray={`${(media / 10) * volta} ${volta}`} transform={`rotate(-90 ${c} ${c})`} />
      )}
      <line x1={c + (r - 5) * Math.cos(angMin)} y1={c + (r - 5) * Math.sin(angMin)}
        x2={c + (r + 5) * Math.cos(angMin)} y2={c + (r + 5) * Math.sin(angMin)} stroke="var(--tinta)" strokeWidth={1.5} />
      <text x={c} y={c} textAnchor="middle" dominantBaseline="central" fontSize={tamanho * 0.27} fontWeight={700} fill="var(--tinta)">
        {media === null ? "—" : nota1(media)}
      </text>
    </svg>
  );
}

/** As quatro notas lado a lado, em barrinhas: o perfil do projetista num relance. */
function Barras({ a }: { a: Pick<Avaliacao, Criterio> }) {
  return (
    <span className="barras-avaliacao" aria-hidden="true">
      {CRITERIOS.map((c) => (
        <span key={c.chave} title={`${c.curto}: ${a[c.chave]}`}
          style={{ height: `${a[c.chave] * 10}%`, background: faixa(a[c.chave]).cor }} />
      ))}
    </span>
  );
}

/** A evolução das médias, da mais antiga à mais recente, com a linha do 6. */
function Tendencia({ avaliacoes, minima }: { avaliacoes: Avaliacao[]; minima: number }) {
  const pontos = [...avaliacoes].reverse();
  if (pontos.length < 2) return null;
  const L = 260, A = 64, m = 6;
  const x = (i: number) => m + (i * (L - 2 * m)) / (pontos.length - 1);
  const y = (v: number) => A - m - ((v - 0) / 10) * (A - 2 * m);
  return (
    <svg className="tendencia" viewBox={`0 0 ${L} ${A}`} role="img" aria-label="Evolução das médias">
      <line x1={0} x2={L} y1={y(minima)} y2={y(minima)} stroke="var(--obsoleto-marca)" strokeDasharray="4 3" strokeWidth={1} />
      <polyline fill="none" stroke="var(--petroleo)" strokeWidth={2} points={pontos.map((p, i) => `${x(i)},${y(p.media)}`).join(" ")} />
      {pontos.map((p, i) => (
        <circle key={p.id} cx={x(i)} cy={y(p.media)} r={3.5} fill={faixa(p.media).cor}>
          <title>{`${formatarData(p.data)} · ${p.empreendimento}: ${nota1(p.media)}`}</title>
        </circle>
      ))}
    </svg>
  );
}

export default function Fornecedores() {
  const [lista, setLista] = useState<Fornecedor[] | null>(null);
  const [opcoes, setOpcoes] = useState<Opcoes | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [escopo, setEscopo] = useState("");
  const [situacao, setSituacao] = useState<"" | Fornecedor["situacao"] | "sem_avaliacao">("");
  const [aberto, setAberto] = useState<number | "novo" | null>(null);

  async function carregar() {
    try {
      const [l, o] = await Promise.all([api.get<Fornecedor[]>("/fornecedores"), api.get<Opcoes>("/fornecedores/opcoes")]);
      setLista(l);
      setOpcoes(o);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível carregar os fornecedores.");
    }
  }
  useEffect(() => {
    void carregar();
  }, []);

  const nomeEscopo = useMemo(() => new Map(opcoes?.escopos.map((e) => [e.codigo, e.nome]) ?? []), [opcoes]);
  const termo = busca.trim().toLowerCase();
  const filtrados = (lista ?? []).filter(
    (f) =>
      (!termo ||
        [f.razao_social, f.nome_fantasia, f.cnpj, f.contato, f.email, f.cod_sienge]
          .some((v) => v?.toLowerCase().includes(termo))) &&
      (!escopo || f.escopos.includes(escopo)) &&
      (!situacao || (situacao === "sem_avaliacao" ? !f.avaliado : f.situacao === situacao)),
  );
  const conta = (s: Fornecedor["situacao"]) => (lista ?? []).filter((f) => f.situacao === s).length;
  const semAvaliacao = (lista ?? []).filter((f) => !f.avaliado).length;

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Qualidade · PRO-FL-002</span>
          <h1>Fornecedores de projetos</h1>
        </div>
        <button className="botao" onClick={() => setAberto("novo")} disabled={!opcoes}>
          Novo fornecedor
        </button>
      </div>

      {erro && <Aviso tom="erro">{erro}</Aviso>}
      {lista === null && !erro && <Carregando texto="Buscando os fornecedores" />}

      {lista && opcoes && (
        <>
          <div className="placar-fornecedores">
            {([
              ["qualificado", "Qualificados", conta("qualificado")],
              ["desqualificado", "Desqualificados", conta("desqualificado")],
              ["pendente", "Qualificação pendente", conta("pendente")],
              ["sem_avaliacao", "Sem avaliação de desempenho", semAvaliacao],
            ] as const).map(([chave, rotulo, n]) => (
              <button key={chave} className={`placar ${chave} ${situacao === chave ? "ativo" : ""}`}
                onClick={() => setSituacao(situacao === chave ? "" : chave)} aria-pressed={situacao === chave}>
                <strong>{n}</strong>
                <span>{rotulo}</span>
              </button>
            ))}
          </div>

          <div className="folha">
            <div className="folha-corpo filtros">
              <label className="campo" style={{ flex: "1 1 260px" }}>
                <span className="rotulo">Buscar</span>
                <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nome, CNPJ, contato, código Sienge" />
              </label>
              <label className="campo">
                <span className="rotulo">Escopo</span>
                <select value={escopo} onChange={(e) => setEscopo(e.target.value)}>
                  <option value="">Todos</option>
                  {opcoes.escopos.map((e) => (
                    <option key={e.codigo} value={e.codigo}>{e.nome}</option>
                  ))}
                </select>
              </label>
            </div>
            {filtrados.length === 0 ? (
              <Vazio titulo={lista.length ? "Nenhum fornecedor com esses filtros" : "Nenhum fornecedor cadastrado"} />
            ) : (
              <div className="tabela-rolagem">
                <table className="tabela tabela-fornecedores">
                  <thead>
                    <tr>
                      <th>Fornecedor</th>
                      <th>CNPJ</th>
                      <th>Contato</th>
                      <th>Escopo</th>
                      <th>Qualificação documental</th>
                      <th>Desempenho</th>
                      <th>Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtrados.map((f) => (
                      <tr key={f.id} className={`linha-clicavel ${f.ativo ? "" : "inativo"}`} onClick={() => setAberto(f.id)}>
                        <td>
                          <button className="nome-fornecedor" onClick={() => setAberto(f.id)}>
                            {f.nome_fantasia || f.razao_social}
                          </button>
                          <span className="silencioso sub-fornecedor">
                            {f.nome_fantasia && f.nome_fantasia !== f.razao_social ? `${f.razao_social} · ` : ""}
                            {f.cod_sienge ? `Sienge ${f.cod_sienge}` : "sem código Sienge"}
                            {!f.ativo && " · inativo"}
                          </span>
                        </td>
                        <td className="mono" style={{ whiteSpace: "nowrap" }}>{f.cnpj ?? "—"}</td>
                        <td className="contato-fornecedor">
                          {f.contato && <span>{f.contato}</span>}
                          {f.email && <span className="silencioso">{f.email}</span>}
                          {f.telefone && <span className="silencioso">{f.telefone}</span>}
                        </td>
                        <td>
                          <span className="chips-escopo">
                            {f.escopos.map((e) => (
                              <span key={e} className="chip-escopo" title={nomeEscopo.get(e)}>{e}</span>
                            ))}
                            {f.padroes.map((p) => (
                              <span key={p} className="chip-escopo padrao">{p}</span>
                            ))}
                          </span>
                        </td>
                        <td>
                          <span className={`selo-fornecedor ${f.qualificacao ?? "pendente"}`}>
                            {f.qualificacao === "qualificado" ? "Qualificado" : f.qualificacao === "desqualificado" ? "Desqualificado" : "À qualificar"}
                          </span>
                        </td>
                        <td>
                          {f.ultima_avaliacao ? (
                            <span className="desempenho-linha">
                              <Mostrador media={f.ultima_avaliacao.media} minima={opcoes.nota_minima} tamanho={40} />
                              <Barras a={f.ultima_avaliacao} />
                              <span className="silencioso" style={{ fontSize: 11.5 }}>
                                {formatarData(f.ultima_avaliacao.data).slice(0, 10)}
                                {f.total_avaliacoes > 1 && <><br />{f.total_avaliacoes} avaliações</>}
                              </span>
                            </span>
                          ) : (
                            <span className="silencioso" style={{ fontSize: 12 }}>À avaliar</span>
                          )}
                        </td>
                        <td>
                          <span className={`selo-fornecedor ${f.situacao}`}>{ROTULO_SITUACAO[f.situacao]}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {aberto !== null && opcoes && (
        <PainelFornecedor
          id={aberto === "novo" ? null : aberto}
          opcoes={opcoes}
          aoMudar={carregar}
          aoCriar={(id) => setAberto(id)}
          aoFechar={() => setAberto(null)}
        />
      )}
    </>
  );
}

function PainelFornecedor({
  id,
  opcoes,
  aoMudar,
  aoCriar,
  aoFechar,
}: {
  id: number | null;
  opcoes: Opcoes;
  aoMudar: () => Promise<void>;
  aoCriar: (id: number) => void;
  aoFechar: () => void;
}) {
  const [f, setF] = useState<Fornecedor | null>(null);
  const [aba, setAba] = useState<"desempenho" | "cadastro" | "avaliar">(id ? "desempenho" : "cadastro");
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setErro(null);
    if (id === null) {
      setF(null);
      setAba("cadastro");
      return;
    }
    api
      .get<Fornecedor>(`/fornecedores/${id}`)
      .then(setF)
      .catch((ex) => setErro(ex instanceof ErroApi ? ex.message : "Não foi possível abrir o fornecedor."));
  }, [id]);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && aoFechar();
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [aoFechar]);

  async function salvo(novo: Fornecedor) {
    setF(novo);
    await aoMudar();
    if (id === null) aoCriar(novo.id);
    setAba("desempenho");
  }

  return (
    <div className="fundo-modal painel-lateral" onMouseDown={(e) => e.target === e.currentTarget && aoFechar()}>
      <aside className="painel-fornecedor" role="dialog" aria-modal="true" aria-label="Fornecedor">
        <header className="painel-fornecedor-topo">
          <div style={{ minWidth: 0 }}>
            <span className="rotulo">{id === null ? "Novo fornecedor" : f?.cod_sienge ? `Sienge ${f.cod_sienge}` : "Fornecedor"}</span>
            <h2 className="titulo-secao" style={{ margin: "2px 0" }}>
              {id === null ? "Cadastro" : (f?.nome_fantasia || f?.razao_social) ?? "…"}
            </h2>
            {f && <span className={`selo-fornecedor ${f.situacao}`}>{ROTULO_SITUACAO[f.situacao]}</span>}
          </div>
          <button className="botao secundario pequeno" onClick={aoFechar}>Fechar</button>
        </header>
        {id !== null && (
          <div className="seletor-visao abas-fornecedor" role="tablist">
            {([["desempenho", "Desempenho"], ["avaliar", "Avaliar entrega"], ["cadastro", "Cadastro"]] as const).map(([v, r]) => (
              <button key={v} role="tab" aria-selected={aba === v} className={aba === v ? "ativo" : ""} onClick={() => setAba(v)}>
                {r}
              </button>
            ))}
          </div>
        )}
        <div className="painel-fornecedor-corpo">
          {erro && <Aviso tom="erro">{erro}</Aviso>}
          {id !== null && !f && !erro && <Carregando texto="Abrindo" />}
          {aba === "cadastro" && (id === null || f) && <Cadastro f={f} opcoes={opcoes} aoSalvar={salvo} />}
          {aba === "desempenho" && f && <Desempenho f={f} opcoes={opcoes} aoAvaliar={() => setAba("avaliar")} />}
          {aba === "avaliar" && f && <Avaliar f={f} opcoes={opcoes} aoSalvar={salvo} />}
        </div>
      </aside>
    </div>
  );
}

function Desempenho({ f, opcoes, aoAvaliar }: { f: Fornecedor; opcoes: Opcoes; aoAvaliar: () => void }) {
  const avaliacoes = f.avaliacoes ?? [];
  const ultima = avaliacoes[0];
  return (
    <>
      <section className="cartao-desempenho">
        <Mostrador media={ultima?.media ?? null} minima={opcoes.nota_minima} tamanho={92} />
        <div style={{ flex: 1, minWidth: 0 }}>
          {ultima ? (
            <>
              <strong className={ultima.continua_qualificado ? "veredito ok" : "veredito nao"}>
                {ultima.continua_qualificado ? "Continua qualificado para novas contratações" : "Desqualificado"}
              </strong>
              <div className="silencioso" style={{ fontSize: 12.5 }}>
                Última avaliação: {ultima.empreendimento} · {formatarData(ultima.data).slice(0, 10)}
              </div>
              {f.total_avaliacoes > 1 && f.media_geral !== null && (
                <div className="silencioso" style={{ fontSize: 12.5 }}>
                  Média geral de {f.total_avaliacoes} avaliações: <strong>{nota1(f.media_geral)}</strong>
                </div>
              )}
              {ultima.motivo && <p className="motivo-desqualificacao">Motivo: {ultima.motivo}</p>}
            </>
          ) : (
            <>
              <strong className="veredito">Ainda não avaliado</strong>
              <div className="silencioso" style={{ fontSize: 12.5 }}>
                A avaliação é feita ao término das entregas contratadas, pelo coordenador de projetos.
              </div>
            </>
          )}
          <button className="botao pequeno" style={{ marginTop: 10 }} onClick={aoAvaliar}>
            Avaliar entrega
          </button>
        </div>
      </section>

      {ultima && (
        <section className="criterios-ultima">
          {CRITERIOS.map((c) => (
            <div key={c.chave} className="criterio-barra">
              <span>{c.nome}</span>
              <span className="trilho">
                <span style={{ width: `${ultima[c.chave] * 10}%`, background: faixa(ultima[c.chave]).cor }} />
              </span>
              <strong>{ultima[c.chave]}</strong>
            </div>
          ))}
        </section>
      )}

      {avaliacoes.length > 1 && (
        <section>
          <h3 className="subtitulo-painel">Evolução</h3>
          <Tendencia avaliacoes={avaliacoes} minima={opcoes.nota_minima} />
        </section>
      )}

      {avaliacoes.length > 0 && (
        <section>
          <h3 className="subtitulo-painel">Histórico</h3>
          <ol className="linha-do-tempo">
            {avaliacoes.map((a) => (
              <li key={a.id} className={a.continua_qualificado ? "" : "nao"}>
                <Mostrador media={a.media} minima={opcoes.nota_minima} tamanho={44} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <strong>{a.empreendimento}</strong>
                  <div className="silencioso" style={{ fontSize: 12 }}>
                    {formatarData(a.data).slice(0, 10)}
                    {a.escopo && ` · ${a.escopo}`}
                    {a.avaliado_por && ` · por ${a.avaliado_por}`}
                  </div>
                  <div className="notas-criterios">
                    {CRITERIOS.map((c) => (
                      <span key={c.chave}>
                        {c.curto} <strong style={{ color: faixa(a[c.chave]).cor }}>{a[c.chave]}</strong>
                      </span>
                    ))}
                  </div>
                  {a.motivo && <p className="motivo-desqualificacao">Motivo: {a.motivo}</p>}
                  {a.comentario && <p className="silencioso" style={{ margin: "4px 0 0", fontSize: 12.5 }}>{a.comentario}</p>}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}

function Avaliar({ f, opcoes, aoSalvar }: { f: Fornecedor; opcoes: Opcoes; aoSalvar: (f: Fornecedor) => Promise<void> }) {
  const { obras } = useSessao();
  const [obraId, setObraId] = useState("");
  const [outro, setOutro] = useState("");
  const [escopo, setEscopo] = useState(f.escopos.length === 1 ? f.escopos[0] : "");
  const [data, setData] = useState(() => new Date().toISOString().slice(0, 10));
  const [notas, setNotas] = useState<Partial<Record<Criterio, number>>>({});
  const [motivo, setMotivo] = useState("");
  const [comentario, setComentario] = useState("");
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [salvando, setSalvando] = useState(false);

  const dadas = CRITERIOS.filter((c) => notas[c.chave] !== undefined);
  const media = dadas.length === CRITERIOS.length
    ? CRITERIOS.reduce((s, c) => s + (notas[c.chave] ?? 0), 0) / CRITERIOS.length
    : null;
  const parcial = dadas.length ? dadas.reduce((s, c) => s + (notas[c.chave] ?? 0), 0) / dadas.length : null;
  const continua = media !== null && media >= opcoes.nota_minima;
  const empreendimentoOk = obraId === "outro" ? outro.trim().length > 1 : obraId !== "";
  const pronto = media !== null && empreendimentoOk && !!data && (continua || motivo.trim());

  async function salvar(e: FormEvent) {
    e.preventDefault();
    if (!pronto) return;
    setSalvando(true);
    setErro(null);
    try {
      const novo = await api.post<Fornecedor>(`/fornecedores/${f.id}/avaliacoes`, {
        obra_id: obraId && obraId !== "outro" ? Number(obraId) : null,
        empreendimento: obraId === "outro" ? outro.trim() : null,
        escopo: escopo || null,
        data: `${data}T12:00:00Z`,
        ...notas,
        motivo: continua ? null : motivo.trim(),
        comentario: comentario.trim() || null,
      });
      await aoSalvar(novo);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível salvar a avaliação."));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <form onSubmit={salvar} className="form-avaliacao">
      <p className="silencioso" style={{ marginTop: 0, fontSize: 12.5 }}>
        Ao término das entregas contratadas, o coordenador de projetos avalia o projetista. A média dos quatro
        critérios diz se ele continua qualificado para novas contratações (mínimo {nota1(opcoes.nota_minima)}).
      </p>
      <div className="filtros">
        <label className="campo" style={{ flex: "1 1 220px" }}>
          <span className="rotulo">Empreendimento</span>
          <select value={obraId} onChange={(e) => setObraId(e.target.value)} required>
            <option value="" disabled>Escolha</option>
            {obras.map((o) => (
              <option key={o.id} value={o.id}>{o.codigo} · {o.nome}</option>
            ))}
            <option value="outro">Outro, fora do sistema…</option>
          </select>
        </label>
        {obraId === "outro" && (
          <label className="campo" style={{ flex: "1 1 200px" }}>
            <span className="rotulo">Nome do empreendimento</span>
            <input value={outro} onChange={(e) => setOutro(e.target.value)} maxLength={200} required />
          </label>
        )}
        <label className="campo">
          <span className="rotulo">Escopo</span>
          <select value={escopo} onChange={(e) => setEscopo(e.target.value)}>
            <option value="">—</option>
            {(f.escopos.length ? f.escopos : opcoes.escopos.map((e) => e.codigo)).map((e) => (
              <option key={e} value={e}>{e}</option>
            ))}
          </select>
        </label>
        <label className="campo">
          <span className="rotulo">Término das entregas</span>
          <input type="date" value={data} onChange={(e) => setData(e.target.value)} required />
        </label>
      </div>

      {CRITERIOS.map((c) => {
        const v = notas[c.chave];
        return (
          <fieldset key={c.chave} className="regua">
            <legend>
              <strong>{c.nome}</strong>
              {v !== undefined && <span style={{ color: faixa(v).cor }}> · {v} — {faixa(v).nome}</span>}
            </legend>
            <span className="silencioso dica-criterio">{c.dica}</span>
            <div className="regua-notas" role="radiogroup" aria-label={c.nome}>
              {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                <button
                  type="button"
                  key={n}
                  role="radio"
                  aria-checked={v === n}
                  className={`nota ${v !== undefined && n <= v ? "cheia" : ""} ${v === n ? "escolhida" : ""}`}
                  style={{ "--cor-nota": faixa(v ?? n).cor } as CSSProperties}
                  onClick={() => setNotas((a) => ({ ...a, [c.chave]: n }))}
                >
                  {n}
                </button>
              ))}
            </div>
            <div className="regua-faixas silencioso" aria-hidden="true">
              <span>Insatisfatório</span>
              <span>Regular</span>
              <span>Bom</span>
              <span>Excelente</span>
            </div>
          </fieldset>
        );
      })}

      <div className={`resultado-avaliacao ${media === null ? "" : continua ? "ok" : "nao"}`}>
        <Mostrador media={media ?? parcial} minima={opcoes.nota_minima} tamanho={76} />
        <div style={{ flex: 1 }}>
          {media === null ? (
            <strong>Dê nota aos {CRITERIOS.length - dadas.length === 4 ? "quatro" : CRITERIOS.length - dadas.length} critérios{dadas.length ? " que faltam" : ""}</strong>
          ) : continua ? (
            <strong>Continua qualificado para novas contratações</strong>
          ) : (
            <strong>Fica desqualificado: registre o motivo</strong>
          )}
          <div className="silencioso" style={{ fontSize: 12.5 }}>
            Média {media !== null ? nota1(media) : parcial !== null ? `parcial ${nota1(parcial)}` : "—"} · mínimo {nota1(opcoes.nota_minima)}
          </div>
        </div>
      </div>

      {media !== null && !continua && (
        <label className="campo" style={{ display: "block" }}>
          <span className="rotulo">Motivo da desqualificação (obrigatório)</span>
          <textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={3} maxLength={4000} required autoFocus />
        </label>
      )}
      <label className="campo" style={{ display: "block" }}>
        <span className="rotulo">Comentário (opcional)</span>
        <textarea value={comentario} onChange={(e) => setComentario(e.target.value)} rows={2} maxLength={4000} />
      </label>
      {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
      <button className="botao" disabled={!pronto || salvando}>
        {salvando ? "Salvando…" : "Salvar avaliação"}
      </button>
    </form>
  );
}

function Cadastro({ f, opcoes, aoSalvar }: { f: Fornecedor | null; opcoes: Opcoes; aoSalvar: (f: Fornecedor) => Promise<void> }) {
  const [d, setD] = useState(() => ({
    cod_sienge: f?.cod_sienge ?? "",
    razao_social: f?.razao_social ?? "",
    nome_fantasia: f?.nome_fantasia ?? "",
    cnpj: f?.cnpj ?? "",
    contato: f?.contato ?? "",
    email: f?.email ?? "",
    telefone: f?.telefone ?? "",
    observacoes: f?.observacoes ?? "",
    registro_conselho: f?.registro_conselho ?? "",
    portfolio: f?.portfolio === null || f?.portfolio === undefined ? "" : f.portfolio ? "sim" : "nao",
    escopos: f?.escopos ?? [],
    padroes: f?.padroes ?? [],
    ativo: f?.ativo ?? true,
  }));
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [salvando, setSalvando] = useState(false);
  const muda = (k: keyof typeof d) => (e: { target: { value: string } }) => setD((x) => ({ ...x, [k]: e.target.value }));
  const alterna = (k: "escopos" | "padroes", c: string) =>
    setD((x) => ({ ...x, [k]: x[k].includes(c) ? x[k].filter((y) => y !== c) : [...x[k], c] }));

  const qualificacao = !d.registro_conselho
    ? null
    : d.registro_conselho !== "NAO" && d.portfolio === "sim"
      ? "qualificado"
      : "desqualificado";

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro(null);
    try {
      const corpo = {
        ...d,
        registro_conselho: d.registro_conselho || null,
        portfolio: d.portfolio === "" ? null : d.portfolio === "sim",
      };
      const novo = f
        ? await api.put<Fornecedor>(`/fornecedores/${f.id}`, corpo)
        : await api.post<Fornecedor>("/fornecedores", corpo);
      await aoSalvar(novo);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível salvar o fornecedor."));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <form onSubmit={salvar} className="form-fornecedor">
      <h3 className="subtitulo-painel">Cadastro</h3>
      <div className="grade-campos">
        <label className="campo largo">
          <span className="rotulo">Razão social</span>
          <input value={d.razao_social} onChange={muda("razao_social")} required minLength={2} maxLength={200} />
        </label>
        <label className="campo largo">
          <span className="rotulo">Nome fantasia</span>
          <input value={d.nome_fantasia} onChange={muda("nome_fantasia")} maxLength={200} />
        </label>
        <label className="campo">
          <span className="rotulo">CNPJ</span>
          <input value={d.cnpj} onChange={muda("cnpj")} maxLength={20} placeholder="00.000.000/0000-00" />
        </label>
        <label className="campo">
          <span className="rotulo">Código Sienge</span>
          <input value={d.cod_sienge} onChange={muda("cod_sienge")} maxLength={20} />
        </label>
        <label className="campo">
          <span className="rotulo">Contato</span>
          <input value={d.contato} onChange={muda("contato")} maxLength={120} />
        </label>
        <label className="campo">
          <span className="rotulo">Telefone</span>
          <input value={d.telefone} onChange={muda("telefone")} maxLength={40} />
        </label>
        <label className="campo largo">
          <span className="rotulo">E-mail</span>
          <input type="email" value={d.email} onChange={muda("email")} maxLength={200} />
        </label>
        <label className="campo largo">
          <span className="rotulo">Observações</span>
          <textarea value={d.observacoes} onChange={muda("observacoes")} rows={2} maxLength={4000} />
        </label>
      </div>

      <h3 className="subtitulo-painel">Qualificação documental</h3>
      <div className="grade-campos">
        <label className="campo">
          <span className="rotulo">Registro no conselho</span>
          <select value={d.registro_conselho} onChange={muda("registro_conselho")}>
            <option value="">Não conferido</option>
            <option value="SIM">Sim</option>
            <option value="NAO">Não</option>
            <option value="NA">Não se aplica</option>
          </select>
        </label>
        <label className="campo">
          <span className="rotulo">Portfólio</span>
          <select value={d.portfolio} onChange={muda("portfolio")}>
            <option value="">Não conferido</option>
            <option value="sim">Sim</option>
            <option value="nao">Não</option>
          </select>
        </label>
        <div className="campo">
          <span className="rotulo">Resultado</span>
          <span className={`selo-fornecedor ${qualificacao ?? "pendente"}`} style={{ alignSelf: "flex-start", marginTop: 6 }}>
            {qualificacao === "qualificado" ? "Qualificado" : qualificacao === "desqualificado" ? "Desqualificado" : "À qualificar"}
          </span>
        </div>
      </div>

      <h3 className="subtitulo-painel">Escopo atendido</h3>
      <div className="chips-escolha">
        {opcoes.escopos.map((e) => (
          <button type="button" key={e.codigo} className={d.escopos.includes(e.codigo) ? "marcado" : ""}
            aria-pressed={d.escopos.includes(e.codigo)} onClick={() => alterna("escopos", e.codigo)} title={e.nome}>
            {e.codigo}
          </button>
        ))}
      </div>
      <h3 className="subtitulo-painel">Padrão do empreendimento</h3>
      <div className="chips-escolha">
        {opcoes.padroes.map((p) => (
          <button type="button" key={p.codigo} className={d.padroes.includes(p.codigo) ? "marcado" : ""}
            aria-pressed={d.padroes.includes(p.codigo)} onClick={() => alterna("padroes", p.codigo)}>
            {p.nome}
          </button>
        ))}
      </div>
      <label className="opcao-aviso" style={{ marginTop: 12 }}>
        <input type="checkbox" checked={d.ativo} onChange={(e) => setD((x) => ({ ...x, ativo: e.target.checked }))} />
        Fornecedor ativo
      </label>
      {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
      <button className="botao" style={{ marginTop: 12 }} disabled={salvando}>
        {salvando ? "Salvando…" : f ? "Salvar cadastro" : "Cadastrar fornecedor"}
      </button>
    </form>
  );
}
